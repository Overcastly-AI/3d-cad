"""``RigidBodyAssemblySolver`` — the deterministic 3D mate solver (design §2.2).

The concrete :class:`~geometry.assembly.protocol.AssemblySolver`. Two paths:

1. **Closed-form tree fast path** (§2.2): when the mate graph is a forest rooted
   at grounded instances and every free instance is *fully located* by its single
   placed parent, poses propagate from ground with NO iterative solve — a
   rotation from the mate's direction correspondences plus a translation from the
   (translation-affine) residual, exact. This is the common bolt-two-parts case.
2. **Numerical fallback** (§2.2): a deterministic damped Levenberg-Marquardt over
   the stacked residual system for coupled / loop / partially-constrained graphs.
   Free instances carry 6 DOF ``(t, q)`` seeded from the authored placement,
   grounded instances are held fixed, and the quaternion is renormalised each
   step (a manifold retraction). Identity (Levenberg) damping keeps the step
   well-defined even when the Jacobian is rank-deficient, so the null space stays
   anchored at the seed — under-constrained assemblies still solve.

**Determinism (RESEARCH §9, non-negotiable):** instances are laid out in
input-list order; mates are processed in ``(order_index, id)`` order; the
Jacobian is a fixed central-difference; LM uses a fixed schedule with no random
restart; every op is float64. Same input in ⇒ bitwise-identical placements out.

**Diagnosis (§2.4)** is computed once, at the final placement, by
:func:`_diagnose` — shared by both paths. ``remaining_dof`` comes from the
Jacobian rank (``6·n_free - rank(J)``); a redundant *mate* is one whose residual
rows add no rank (greedy, in processing order); a conflict is a consistent
stationary point with irreducible residual, naming the offending mates.
"""

from __future__ import annotations

import math
import uuid

import numpy as np
from numpy.typing import NDArray

from geometry.assembly.protocol import (
    AssemblyDefinitionError,
    AssemblySolveDiagnosis,
    AssemblySolveInput,
    AssemblySolveMethod,
    AssemblySolveResult,
    AssemblySolveStatus,
    SolvedInstancePlacement,
    SolverInstance,
)
from geometry.assembly.residuals import CompiledMate, compile_mate
from geometry.assembly.transform import (
    Pose,
    matrix_to_quat,
    normalize,
)

Vector = NDArray[np.float64]
Matrix = NDArray[np.float64]

# --- tuned, documented tolerances (never ad-hoc; RESEARCH §9) --------------------

#: Residual 2-norm below which the mate system is considered SATISFIED. Consistent
#: systems converge far below this (~1e-12); a conflict leaves an irreducible
#: residual orders of magnitude larger, so this cleanly separates the two.
SATISFIED_TOL = 1e-7

#: Gradient (‖Jᵀr‖∞) below which LM is at a stationary point. A conflict is a
#: stationary point with residual > SATISFIED_TOL (converged, best-fit);
#: exceeding this after the iteration cap is ``not_converged``.
STATIONARY_GRAD_TOL = 1e-7

#: Central-difference step for the numeric Jacobian (RESEARCH §9 determinism —
#: fixed, so the linearisation is reproducible).
FD_STEP = 1e-5

#: Singular values below ``RANK_REL_TOL · sigma_max`` are treated as zero when
#: counting Jacobian rank (→ remaining DOF / redundancy). Chosen well above the
#: finite-difference noise floor and well below any real constraint's singular
#: value for the documented golden geometry.
RANK_REL_TOL = 1e-6

#: Two directions with cross-product norm below this are treated as parallel
#: (the closed-form rotation needs two independent correspondences).
PARALLEL_TOL = 1e-6

# --- LM schedule (fixed → deterministic) ----------------------------------------
_LM_LAMBDA0 = 1e-3
_LM_LAMBDA_MIN = 1e-12
_LM_LAMBDA_MAX = 1e12
_LM_NU = 10.0
_LM_MAX_ITERS = 200
_LM_MAX_INNER = 40


def _numeric_rank(matrix: Matrix) -> int:
    """Rank of ``matrix`` via SVD with the documented relative tolerance."""
    if matrix.size == 0:
        return 0
    s = np.linalg.svd(matrix, compute_uv=False)
    if s.size == 0 or s[0] == 0.0:
        return 0
    return int(np.count_nonzero(s > RANK_REL_TOL * s[0]))


def _residual_vector(mates: list[CompiledMate], poses: list[Pose]) -> Vector:
    """Stack every mate's world-frame residual (mates in processing order)."""
    if not mates:
        return np.zeros(0, dtype=np.float64)
    blocks = [m.residual(poses[m.idx_a], poses[m.idx_b]) for m in mates]
    return np.concatenate(blocks)


def _jacobian(
    mates: list[CompiledMate], poses: list[Pose], free_indices: list[int]
) -> Matrix:
    """Central-difference Jacobian of the residual wrt each free instance's 6 DOF.

    Columns are laid out ``[δt, δω]`` per free instance, free instances in
    input-list order — the deterministic variable ordering.
    """
    total_rows = sum(m.rows for m in mates)
    n = 6 * len(free_indices)
    jac = np.zeros((total_rows, n), dtype=np.float64)
    if total_rows == 0 or n == 0:
        return jac
    for slot, inst in enumerate(free_indices):
        base_pose = poses[inst]
        for k in range(6):
            dt = np.zeros(3, dtype=np.float64)
            dw = np.zeros(3, dtype=np.float64)
            if k < 3:
                dt[k] = FD_STEP
            else:
                dw[k - 3] = FD_STEP
            plus = list(poses)
            minus = list(poses)
            plus[inst] = base_pose.retract(dt, dw)
            minus[inst] = base_pose.retract(-dt, -dw)
            column = (
                _residual_vector(mates, plus) - _residual_vector(mates, minus)
            ) / (2.0 * FD_STEP)
            jac[:, 6 * slot + k] = column
    return jac


def _apply_delta(
    poses: list[Pose], delta: Vector, free_indices: list[int]
) -> list[Pose]:
    """Retract each free instance's pose by its 6-DOF slice of ``delta``."""
    out = list(poses)
    for slot, inst in enumerate(free_indices):
        seg = delta[6 * slot : 6 * slot + 6]
        out[inst] = poses[inst].retract(seg[:3], seg[3:6])
    return out


def _lm_solve(
    mates: list[CompiledMate], seed_poses: list[Pose], free_indices: list[int]
) -> tuple[list[Pose], bool]:
    """Deterministic Levenberg-Marquardt from the authored seed.

    Returns the solved poses and whether the solve reached a stationary point
    (residual satisfied OR gradient below tolerance). Grounded instances (absent
    from ``free_indices``) are never perturbed.
    """
    poses = list(seed_poses)
    n = 6 * len(free_indices)
    if n == 0:
        return poses, True

    r = _residual_vector(mates, poses)
    cost = float(r @ r)
    lam = _LM_LAMBDA0
    eye = np.eye(n, dtype=np.float64)

    for _ in range(_LM_MAX_ITERS):
        if math.sqrt(cost) < SATISFIED_TOL:
            break
        jac = _jacobian(mates, poses, free_indices)
        grad = jac.T @ r
        if float(np.max(np.abs(grad))) < STATIONARY_GRAD_TOL:
            break
        jtj = jac.T @ jac
        accepted = False
        while lam <= _LM_LAMBDA_MAX:
            try:
                delta = np.linalg.solve(jtj + lam * eye, -grad)
            except np.linalg.LinAlgError:
                lam *= _LM_NU
                continue
            candidate = _apply_delta(poses, delta, free_indices)
            r_new = _residual_vector(mates, candidate)
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                poses, r, cost = candidate, r_new, cost_new
                lam = max(lam / _LM_NU, _LM_LAMBDA_MIN)
                accepted = True
                break
            lam *= _LM_NU
        if not accepted:
            break

    if math.sqrt(cost) < SATISFIED_TOL:
        return poses, True
    grad = _jacobian(mates, poses, free_indices).T @ r
    converged = float(np.max(np.abs(grad))) < STATIONARY_GRAD_TOL
    return poses, converged


# --- closed-form tree fast path -------------------------------------------------


def _frame(u: Vector, v: Vector) -> Matrix | None:
    """Right-handed orthonormal frame with column 1 = ``u`` and ``v`` in the
    span of columns 1-2. ``None`` if ``v`` is parallel to ``u`` (degenerate)."""
    e1 = normalize(u)
    v_perp = v - float(np.dot(v, e1)) * e1
    if float(np.linalg.norm(v_perp)) < PARALLEL_TOL:
        return None
    e2 = normalize(v_perp)
    e3 = np.cross(e1, e2)
    return np.column_stack([e1, e2, e3])


def _closed_form_child(
    parent_pose: Pose,
    pair_mates: list[CompiledMate],
    child_idx: int,
    seed_child: Pose,
) -> Pose | None:
    """Solve one free instance's pose from a single placed parent, in closed form.

    Returns the child pose if the pair's mates FULLY locate it (rotation from ≥2
    independent direction correspondences, translation full-rank, residual within
    tolerance); ``None`` otherwise (→ the caller falls to the numeric solver).
    """

    def pair_residual(child_pose: Pose) -> Vector:
        blocks: list[Vector] = []
        for m in pair_mates:
            pose_a = child_pose if m.idx_a == child_idx else parent_pose
            pose_b = child_pose if m.idx_b == child_idx else parent_pose
            blocks.append(m.residual(pose_a, pose_b))
        return np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float64)

    # A lock fully fixes the relative pose — compose directly from the parent.
    for m in pair_mates:
        if m.kind == "lock":
            assert m.lock_rel is not None
            if m.idx_b == child_idx:  # child == b: b = a ∘ rel = parent ∘ rel
                child_pose = parent_pose.compose(m.lock_rel)
            else:  # child == a: a = b ∘ rel⁻¹ = parent ∘ rel⁻¹
                child_pose = parent_pose.compose(m.lock_rel.inverse())
            if float(np.linalg.norm(pair_residual(child_pose))) < SATISFIED_TOL:
                return child_pose
            return None

    # Otherwise gather rotational direction correspondences (child-local → world).
    correspondences: list[tuple[Vector, Vector]] = []
    for m in pair_mates:
        if m.kind == "angle":
            return None  # an angle mate does not fully locate — defer to numeric
        if m.idx_a == child_idx:
            child_dir, parent_dir_world = m.dir_a, parent_pose.apply_direction(m.dir_b)
        else:
            child_dir, parent_dir_world = m.dir_b, parent_pose.apply_direction(m.dir_a)
        if m.kind == "coincident":
            target = -parent_dir_world if m.flush else parent_dir_world
        else:  # concentric: axes collinear, ± sign resolved by the seed pose
            seed_dir = seed_child.apply_direction(child_dir)
            sign = 1.0 if float(np.dot(seed_dir, parent_dir_world)) >= 0.0 else -1.0
            target = sign * parent_dir_world
        correspondences.append((normalize(child_dir), normalize(target)))

    if len(correspondences) < 2:
        return None  # rotation underdetermined by a single correspondence

    s1, t1 = correspondences[0]
    second: tuple[Vector, Vector] | None = None
    for s, t in correspondences[1:]:
        if float(np.linalg.norm(np.cross(s1, s))) > PARALLEL_TOL:
            second = (s, t)
            break
    if second is None:
        return None  # all correspondences parallel → rotation underdetermined
    source_frame = _frame(s1, second[0])
    target_frame = _frame(t1, second[1])
    if source_frame is None or target_frame is None:
        return None  # inconsistent correspondence angles
    rot = target_frame @ source_frame.T
    q = matrix_to_quat(rot)

    # Translation is affine in t: r(t) = r0 + M t. Solve least-squares, require
    # full translational rank, then verify the whole pair residual vanishes.
    r0 = pair_residual(Pose(t=np.zeros(3, dtype=np.float64), q=q))
    m_cols = np.zeros((r0.size, 3), dtype=np.float64)
    for k in range(3):
        e = np.zeros(3, dtype=np.float64)
        e[k] = 1.0
        m_cols[:, k] = pair_residual(Pose(t=e, q=q)) - r0
    if _numeric_rank(m_cols) < 3:
        return None
    t_solution, *_ = np.linalg.lstsq(m_cols, -r0, rcond=None)
    child_pose = Pose(t=t_solution, q=q)
    if float(np.linalg.norm(pair_residual(child_pose))) < SATISFIED_TOL:
        return child_pose
    return None


def _try_fast_path(
    instances: list[SolverInstance],
    mates: list[CompiledMate],
    seed_poses: list[Pose],
    free_indices: list[int],
) -> list[Pose] | None:
    """Attempt the closed-form tree solve; ``None`` if it does not apply.

    Applies only to a forest of instance pairs rooted at grounded instances where
    each free instance is fully located by its single placed parent. Any loop
    (a free instance with ≥2 placed neighbours), a floating component, or a
    not-fully-located child returns ``None`` → the numeric solver runs.
    """
    n_inst = len(instances)
    grounded = [i for i in range(n_inst) if instances[i].grounded]
    if not grounded:
        return None

    pairs: dict[frozenset[int], list[CompiledMate]] = {}
    for m in mates:
        pairs.setdefault(frozenset((m.idx_a, m.idx_b)), []).append(m)

    placed: dict[int, Pose] = {i: seed_poses[i] for i in grounded}
    remaining = set(free_indices)
    progress = True
    while remaining and progress:
        progress = False
        for i in free_indices:  # deterministic order
            if i not in remaining:
                continue
            neighbours = {next(iter(key - {i})) for key in pairs if i in key}
            placed_neighbours = [j for j in neighbours if j in placed]
            if len(placed_neighbours) == 0:
                continue
            if len(placed_neighbours) >= 2:
                return None  # coupled through multiple placed parents → numeric
            parent = placed_neighbours[0]
            pose = _closed_form_child(
                placed[parent], pairs[frozenset((i, parent))], i, seed_poses[i]
            )
            if pose is None:
                return None
            placed[i] = pose
            remaining.discard(i)
            progress = True

    if remaining:
        return None
    return [placed[i] for i in range(n_inst)]


# --- diagnosis (shared by both paths) -------------------------------------------


def _redundant_mates(mates: list[CompiledMate], jac: Matrix) -> list[uuid.UUID]:
    """Mate ids whose Jacobian rows add no rank, greedily in processing order.

    A *whole* mate is redundant when the constraints already kept fully span its
    rows — it can be removed and the assembly still solves (design §2.4,
    ``removable``). The greedy front-to-back order mirrors the sketch solver's
    input-order convention.
    """
    redundant: list[uuid.UUID] = []
    kept = np.zeros((0, jac.shape[1]), dtype=np.float64)
    base_rank = 0
    offset = 0
    for m in mates:
        rows = jac[offset : offset + m.rows]
        offset += m.rows
        stacked = np.vstack([kept, rows])
        if _numeric_rank(stacked) == base_rank:
            redundant.append(m.mate_id)
        else:
            kept = stacked
            base_rank = _numeric_rank(kept)
    return redundant


def _diagnose(
    mates: list[CompiledMate],
    poses: list[Pose],
    free_indices: list[int],
    converged: bool,
) -> tuple[AssemblySolveStatus, AssemblySolveDiagnosis | None]:
    """Classify the solve at its final placement (design §2.4)."""
    n = 6 * len(free_indices)
    r = _residual_vector(mates, poses)
    rnorm = float(np.linalg.norm(r)) if r.size else 0.0

    if rnorm > SATISFIED_TOL:
        if not converged:
            return "not_converged", AssemblySolveDiagnosis(
                remaining_dof=0,
                message="the solver did not converge to tolerance",
                suggested_fix="Loosen or remove conflicting mates and retry",
            )
        offending: list[uuid.UUID] = []
        offset = 0
        for m in mates:
            seg = r[offset : offset + m.rows]
            offset += m.rows
            if float(np.linalg.norm(seg)) > SATISFIED_TOL:
                offending.append(m.mate_id)
        if not offending:  # residual spread thinly across mates
            offending = [m.mate_id for m in mates]
        return "conflicting", AssemblySolveDiagnosis(
            classification="conflicting",
            removable=False,
            remaining_dof=0,
            conflicting_mates=offending,
            message=f"mates {offending} are mutually unsatisfiable",
            suggested_fix=f"Remove or relax mate {offending[0]}",
        )

    if n == 0:
        return "well_constrained", None

    jac = _jacobian(mates, poses, free_indices)
    remaining_dof = n - _numeric_rank(jac)
    if remaining_dof > 0:
        return "under_constrained", AssemblySolveDiagnosis(
            remaining_dof=remaining_dof,
            message=(
                f"{remaining_dof} degree(s) of freedom remain; free instances "
                "left at their seed placement"
            ),
            suggested_fix="Add mates to remove the remaining degrees of freedom",
        )

    redundant = _redundant_mates(mates, jac)
    if redundant:
        return "over_constrained", AssemblySolveDiagnosis(
            classification="redundant",
            removable=True,
            remaining_dof=0,
            redundant_mates=redundant,
            message=f"consistent but over-constrained: mate(s) {redundant} redundant",
            suggested_fix=f"Remove mate {redundant[0]}",
        )
    return "well_constrained", None


class RigidBodyAssemblySolver:
    """Deterministic rigid-body mate solver (design §2.2). See the module docs."""

    def solve(self, problem: AssemblySolveInput) -> AssemblySolveResult:
        instances = problem.instances
        if not instances:
            raise AssemblyDefinitionError("assembly has no instances")

        index_of: dict[uuid.UUID, int] = {}
        for i, inst in enumerate(instances):
            if inst.instance_id in index_of:
                raise AssemblyDefinitionError(
                    f"duplicate instance id {inst.instance_id}"
                )
            index_of[inst.instance_id] = i

        seed_poses = [Pose.from_placement(inst.placement) for inst in instances]
        ordered = sorted(
            problem.mates, key=lambda sm: (sm.order_index, str(sm.mate_id))
        )
        compiled = [compile_mate(sm, index_of, seed_poses) for sm in ordered]
        free_indices = [i for i, inst in enumerate(instances) if not inst.grounded]

        method: AssemblySolveMethod
        fast = _try_fast_path(instances, compiled, seed_poses, free_indices)
        if fast is not None:
            poses, method, converged = fast, "closed_form", True
        else:
            poses, converged = _lm_solve(compiled, seed_poses, free_indices)
            method = "numeric"

        status, diagnosis = _diagnose(compiled, poses, free_indices, converged)
        placements = [
            SolvedInstancePlacement(
                instance_id=instances[i].instance_id,
                placement=poses[i].to_placement(),
            )
            for i in range(len(instances))
        ]
        return AssemblySolveResult(
            status=status,
            method=method,
            placements=placements,
            diagnosis=diagnosis,
        )
