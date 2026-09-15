# GENERATED — do not edit; run `just gen`.
"""Gateway operation table for the Python scripting client.

Source contract: packages/contracts/gateway.openapi.json.

One :class:`~loft._operation.Operation` per gateway route. The library
never spells a URL or a method inline — it names an operation here — so a
route that moves is a regenerated table and a pyright error at the call
site, not a 404 a user's script discovers at runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from loft._operation import Operation

GET_ASSEMBLIES: Final = Operation(
    operation_id="list_assemblies_api_v1_assemblies_get",
    method="GET",
    path="/api/v1/assemblies",
    request_model=None,
    response_model="AssemblyListResponse",
    path_params=(),
    required_query=(),
)

POST_ASSEMBLIES: Final = Operation(
    operation_id="create_assembly_api_v1_assemblies_post",
    method="POST",
    path="/api/v1/assemblies",
    request_model="AssemblyCreate",
    response_model="AssemblyResponse",
    path_params=(),
    required_query=(),
)

POST_ASSEMBLIES_IMPORT: Final = Operation(
    operation_id="import_assembly_step_api_v1_assemblies_import_post",
    method="POST",
    path="/api/v1/assemblies/import",
    request_model=None,
    response_model=None,
    path_params=(),
    required_query=(),
)

GET_ASSEMBLIES_ASSEMBLY_ID: Final = Operation(
    operation_id="get_assembly_api_v1_assemblies__assembly_id__get",
    method="GET",
    path="/api/v1/assemblies/{assembly_id}",
    request_model=None,
    response_model="AssemblyGraphResponse",
    path_params=("assembly_id",),
    required_query=(),
)

DELETE_ASSEMBLIES_ASSEMBLY_ID: Final = Operation(
    operation_id="delete_assembly_api_v1_assemblies__assembly_id__delete",
    method="DELETE",
    path="/api/v1/assemblies/{assembly_id}",
    request_model=None,
    response_model=None,
    path_params=("assembly_id",),
    required_query=(),
)

PATCH_ASSEMBLIES_ASSEMBLY_ID: Final = Operation(
    operation_id="update_assembly_api_v1_assemblies__assembly_id__patch",
    method="PATCH",
    path="/api/v1/assemblies/{assembly_id}",
    request_model="AssemblyUpdate",
    response_model="AssemblyResponse",
    path_params=("assembly_id",),
    required_query=(),
)

GET_ASSEMBLIES_ASSEMBLY_ID_BOM: Final = Operation(
    operation_id="get_assembly_bom_api_v1_assemblies__assembly_id__bom_get",
    method="GET",
    path="/api/v1/assemblies/{assembly_id}/bom",
    request_model=None,
    response_model="AssemblyBomResponse",
    path_params=("assembly_id",),
    required_query=(),
)

POST_ASSEMBLIES_ASSEMBLY_ID_DUPLICATE: Final = Operation(
    operation_id="duplicate_assembly_api_v1_assemblies__assembly_id__duplicate_post",
    method="POST",
    path="/api/v1/assemblies/{assembly_id}/duplicate",
    request_model=None,
    response_model="AssemblyResponse",
    path_params=("assembly_id",),
    required_query=(),
)

GET_ASSEMBLIES_ASSEMBLY_ID_EXTENTS: Final = Operation(
    operation_id="get_assembly_extents_api_v1_assemblies__assembly_id__extents_get",
    method="GET",
    path="/api/v1/assemblies/{assembly_id}/extents",
    request_model=None,
    response_model="AssemblyExtentsResponse",
    path_params=("assembly_id",),
    required_query=(),
)

POST_ASSEMBLIES_ASSEMBLY_ID_INSTANCES: Final = Operation(
    operation_id="create_instance_api_v1_assemblies__assembly_id__instances_post",
    method="POST",
    path="/api/v1/assemblies/{assembly_id}/instances",
    request_model="InstanceCreate",
    response_model="InstanceMutationResponse",
    path_params=("assembly_id",),
    required_query=(),
)

DELETE_ASSEMBLIES_ASSEMBLY_ID_INSTANCES_INSTANCE_ID: Final = Operation(
    operation_id="delete_instance_api_v1_assemblies__assembly_id__instances__instance_id__delete",
    method="DELETE",
    path="/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
    request_model=None,
    response_model="AssemblyGraphResponse",
    path_params=("assembly_id", "instance_id",),
    required_query=("expected_version",),
)

PATCH_ASSEMBLIES_ASSEMBLY_ID_INSTANCES_INSTANCE_ID: Final = Operation(
    operation_id="update_instance_api_v1_assemblies__assembly_id__instances__instance_id__patch",
    method="PATCH",
    path="/api/v1/assemblies/{assembly_id}/instances/{instance_id}",
    request_model="InstanceUpdate",
    response_model="InstanceMutationResponse",
    path_params=("assembly_id", "instance_id",),
    required_query=(),
)

POST_ASSEMBLIES_ASSEMBLY_ID_MATES: Final = Operation(
    operation_id="create_mate_api_v1_assemblies__assembly_id__mates_post",
    method="POST",
    path="/api/v1/assemblies/{assembly_id}/mates",
    request_model="MateCreate",
    response_model="MateMutationResponse",
    path_params=("assembly_id",),
    required_query=(),
)

DELETE_ASSEMBLIES_ASSEMBLY_ID_MATES_MATE_ID: Final = Operation(
    operation_id="delete_mate_api_v1_assemblies__assembly_id__mates__mate_id__delete",
    method="DELETE",
    path="/api/v1/assemblies/{assembly_id}/mates/{mate_id}",
    request_model=None,
    response_model="AssemblyGraphResponse",
    path_params=("assembly_id", "mate_id",),
    required_query=("expected_version",),
)

POST_ASSEMBLIES_ASSEMBLY_ID_MOVE: Final = Operation(
    operation_id="move_assembly_api_v1_assemblies__assembly_id__move_post",
    method="POST",
    path="/api/v1/assemblies/{assembly_id}/move",
    request_model="DocumentMove",
    response_model="AssemblyResponse",
    path_params=("assembly_id",),
    required_query=(),
)

POST_ASSEMBLIES_ASSEMBLY_ID_REDO: Final = Operation(
    operation_id="redo_assembly_api_v1_assemblies__assembly_id__redo_post",
    method="POST",
    path="/api/v1/assemblies/{assembly_id}/redo",
    request_model="AssemblyUndoRedoRequest",
    response_model="AssemblyGraphResponse",
    path_params=("assembly_id",),
    required_query=(),
)

POST_ASSEMBLIES_ASSEMBLY_ID_UNDO: Final = Operation(
    operation_id="undo_assembly_api_v1_assemblies__assembly_id__undo_post",
    method="POST",
    path="/api/v1/assemblies/{assembly_id}/undo",
    request_model="AssemblyUndoRedoRequest",
    response_model="AssemblyGraphResponse",
    path_params=("assembly_id",),
    required_query=(),
)

POST_AUTH_LOGIN: Final = Operation(
    operation_id="login_api_v1_auth_login_post",
    method="POST",
    path="/api/v1/auth/login",
    request_model="LoginRequest",
    response_model="AuthTokenResponse",
    path_params=(),
    required_query=(),
)

GET_AUTH_ME: Final = Operation(
    operation_id="me_api_v1_auth_me_get",
    method="GET",
    path="/api/v1/auth/me",
    request_model=None,
    response_model="UserResponse",
    path_params=(),
    required_query=(),
)

POST_AUTH_REGISTER: Final = Operation(
    operation_id="register_api_v1_auth_register_post",
    method="POST",
    path="/api/v1/auth/register",
    request_model="RegisterRequest",
    response_model="AuthTokenResponse",
    path_params=(),
    required_query=(),
)

GET_DRAWINGS: Final = Operation(
    operation_id="list_drawings_api_v1_drawings_get",
    method="GET",
    path="/api/v1/drawings",
    request_model=None,
    response_model="DrawingListResponse",
    path_params=(),
    required_query=(),
)

POST_DRAWINGS: Final = Operation(
    operation_id="create_drawing_api_v1_drawings_post",
    method="POST",
    path="/api/v1/drawings",
    request_model="DrawingCreate",
    response_model="DrawingResponse",
    path_params=(),
    required_query=(),
)

GET_DRAWINGS_DRAWING_ID: Final = Operation(
    operation_id="get_drawing_api_v1_drawings__drawing_id__get",
    method="GET",
    path="/api/v1/drawings/{drawing_id}",
    request_model=None,
    response_model="DrawingTreeResponse",
    path_params=("drawing_id",),
    required_query=(),
)

DELETE_DRAWINGS_DRAWING_ID: Final = Operation(
    operation_id="delete_drawing_api_v1_drawings__drawing_id__delete",
    method="DELETE",
    path="/api/v1/drawings/{drawing_id}",
    request_model=None,
    response_model=None,
    path_params=("drawing_id",),
    required_query=(),
)

PATCH_DRAWINGS_DRAWING_ID: Final = Operation(
    operation_id="update_drawing_api_v1_drawings__drawing_id__patch",
    method="PATCH",
    path="/api/v1/drawings/{drawing_id}",
    request_model="DrawingUpdate",
    response_model="DrawingResponse",
    path_params=("drawing_id",),
    required_query=(),
)

DELETE_DRAWINGS_DRAWING_ID_ANNOTATIONS_ANNOTATION_ID: Final = Operation(
    operation_id="delete_annotation_api_v1_drawings__drawing_id__annotations__annotation_id__delete",
    method="DELETE",
    path="/api/v1/drawings/{drawing_id}/annotations/{annotation_id}",
    request_model=None,
    response_model="DrawingTreeResponse",
    path_params=("drawing_id", "annotation_id",),
    required_query=("expected_version",),
)

GET_DRAWINGS_DRAWING_ID_BOM: Final = Operation(
    operation_id="get_drawing_bom_api_v1_drawings__drawing_id__bom_get",
    method="GET",
    path="/api/v1/drawings/{drawing_id}/bom",
    request_model=None,
    response_model="DrawingBomResponse",
    path_params=("drawing_id",),
    required_query=(),
)

DELETE_DRAWINGS_DRAWING_ID_DIMENSIONS_DIMENSION_ID: Final = Operation(
    operation_id="delete_dimension_api_v1_drawings__drawing_id__dimensions__dimension_id__delete",
    method="DELETE",
    path="/api/v1/drawings/{drawing_id}/dimensions/{dimension_id}",
    request_model=None,
    response_model="DrawingTreeResponse",
    path_params=("drawing_id", "dimension_id",),
    required_query=("expected_version",),
)

POST_DRAWINGS_DRAWING_ID_DUPLICATE: Final = Operation(
    operation_id="duplicate_drawing_api_v1_drawings__drawing_id__duplicate_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/duplicate",
    request_model=None,
    response_model="DrawingResponse",
    path_params=("drawing_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_EXPORT: Final = Operation(
    operation_id="export_drawing_api_v1_drawings__drawing_id__export_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/export",
    request_model=None,
    response_model=None,
    path_params=("drawing_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_MOVE: Final = Operation(
    operation_id="move_drawing_api_v1_drawings__drawing_id__move_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/move",
    request_model="DocumentMove",
    response_model="DrawingResponse",
    path_params=("drawing_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_SHEET: Final = Operation(
    operation_id="compose_drawing_sheet_api_v1_drawings__drawing_id__sheet_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/sheet",
    request_model=None,
    response_model="ComposedSheet",
    path_params=("drawing_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_SHEETS: Final = Operation(
    operation_id="create_sheet_api_v1_drawings__drawing_id__sheets_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/sheets",
    request_model="SheetCreate",
    response_model="SheetMutationResponse",
    path_params=("drawing_id",),
    required_query=(),
)

DELETE_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID: Final = Operation(
    operation_id="delete_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__delete",
    method="DELETE",
    path="/api/v1/drawings/{drawing_id}/sheets/{sheet_id}",
    request_model=None,
    response_model="DrawingTreeResponse",
    path_params=("drawing_id", "sheet_id",),
    required_query=("expected_version",),
)

PATCH_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID: Final = Operation(
    operation_id="update_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__patch",
    method="PATCH",
    path="/api/v1/drawings/{drawing_id}/sheets/{sheet_id}",
    request_model="SheetUpdate",
    response_model="SheetMutationResponse",
    path_params=("drawing_id", "sheet_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID_ANNOTATIONS: Final = Operation(
    operation_id="create_annotation_api_v1_drawings__drawing_id__sheets__sheet_id__annotations_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/annotations",
    request_model="AnnotationCreate",
    response_model="AnnotationMutationResponse",
    path_params=("drawing_id", "sheet_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID_VIEWS: Final = Operation(
    operation_id="create_view_api_v1_drawings__drawing_id__sheets__sheet_id__views_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/sheets/{sheet_id}/views",
    request_model="ViewCreate",
    response_model="ViewMutationResponse",
    path_params=("drawing_id", "sheet_id",),
    required_query=(),
)

DELETE_DRAWINGS_DRAWING_ID_VIEWS_VIEW_ID: Final = Operation(
    operation_id="delete_view_api_v1_drawings__drawing_id__views__view_id__delete",
    method="DELETE",
    path="/api/v1/drawings/{drawing_id}/views/{view_id}",
    request_model=None,
    response_model="DrawingTreeResponse",
    path_params=("drawing_id", "view_id",),
    required_query=("expected_version",),
)

PATCH_DRAWINGS_DRAWING_ID_VIEWS_VIEW_ID: Final = Operation(
    operation_id="update_view_api_v1_drawings__drawing_id__views__view_id__patch",
    method="PATCH",
    path="/api/v1/drawings/{drawing_id}/views/{view_id}",
    request_model="ViewUpdate",
    response_model="ViewMutationResponse",
    path_params=("drawing_id", "view_id",),
    required_query=(),
)

POST_DRAWINGS_DRAWING_ID_VIEWS_VIEW_ID_DIMENSIONS: Final = Operation(
    operation_id="create_dimension_api_v1_drawings__drawing_id__views__view_id__dimensions_post",
    method="POST",
    path="/api/v1/drawings/{drawing_id}/views/{view_id}/dimensions",
    request_model="DimensionCreate",
    response_model="DimensionMutationResponse",
    path_params=("drawing_id", "view_id",),
    required_query=(),
)

GET_FOLDERS: Final = Operation(
    operation_id="list_folders_api_v1_folders_get",
    method="GET",
    path="/api/v1/folders",
    request_model=None,
    response_model="FolderListResponse",
    path_params=(),
    required_query=("kind",),
)

POST_FOLDERS: Final = Operation(
    operation_id="create_folder_api_v1_folders_post",
    method="POST",
    path="/api/v1/folders",
    request_model="FolderCreate",
    response_model="FolderResponse",
    path_params=(),
    required_query=(),
)

DELETE_FOLDERS_FOLDER_ID: Final = Operation(
    operation_id="delete_folder_api_v1_folders__folder_id__delete",
    method="DELETE",
    path="/api/v1/folders/{folder_id}",
    request_model=None,
    response_model=None,
    path_params=("folder_id",),
    required_query=(),
)

PATCH_FOLDERS_FOLDER_ID: Final = Operation(
    operation_id="rename_folder_api_v1_folders__folder_id__patch",
    method="PATCH",
    path="/api/v1/folders/{folder_id}",
    request_model="FolderRename",
    response_model="FolderResponse",
    path_params=("folder_id",),
    required_query=(),
)

POST_FOLDERS_FOLDER_ID_MOVE: Final = Operation(
    operation_id="move_folder_api_v1_folders__folder_id__move_post",
    method="POST",
    path="/api/v1/folders/{folder_id}/move",
    request_model="FolderMove",
    response_model="FolderResponse",
    path_params=("folder_id",),
    required_query=(),
)

POST_GEOMETRY_ASSEMBLY_EVALUATE: Final = Operation(
    operation_id="assembly_evaluate_api_v1_geometry_assembly_evaluate_post",
    method="POST",
    path="/api/v1/geometry/assembly/evaluate",
    request_model="EvaluateAssemblyRequest",
    response_model="EvaluateAssemblyResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_ASSEMBLY_EXPORT: Final = Operation(
    operation_id="assembly_export_api_v1_geometry_assembly_export_post",
    method="POST",
    path="/api/v1/geometry/assembly/export",
    request_model="ExportAssemblyRequest",
    response_model=None,
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_ASSEMBLY_INTERFERENCE: Final = Operation(
    operation_id="assembly_interference_api_v1_geometry_assembly_interference_post",
    method="POST",
    path="/api/v1/geometry/assembly/interference",
    request_model="EvaluateAssemblyRequest",
    response_model="InterferenceResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_DRAWING_EVALUATE: Final = Operation(
    operation_id="drawing_evaluate_api_v1_geometry_drawing_evaluate_post",
    method="POST",
    path="/api/v1/geometry/drawing/evaluate",
    request_model="EvaluateDrawingViewsRequest",
    response_model="EvaluateDrawingViewsResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_EXPORT: Final = Operation(
    operation_id="export_api_v1_geometry_export_post",
    method="POST",
    path="/api/v1/geometry/export",
    request_model="ExportRequest",
    response_model=None,
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_MEASURE: Final = Operation(
    operation_id="measure_api_v1_geometry_measure_post",
    method="POST",
    path="/api/v1/geometry/measure",
    request_model="MeasureRequest",
    response_model="MeasureResult",
    path_params=(),
    required_query=(),
)

GET_GEOMETRY_MESHES_MESH_GLB_ID: Final = Operation(
    operation_id="fetch_mesh_api_v1_geometry_meshes__mesh_glb_id__get",
    method="GET",
    path="/api/v1/geometry/meshes/{mesh_glb_id}",
    request_model=None,
    response_model=None,
    path_params=("mesh_glb_id",),
    required_query=(),
)

POST_GEOMETRY_OVERLAY: Final = Operation(
    operation_id="overlay_api_v1_geometry_overlay_post",
    method="POST",
    path="/api/v1/geometry/overlay",
    request_model="OverlayRequest",
    response_model="OverlayResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_PREFETCH: Final = Operation(
    operation_id="prefetch_api_v1_geometry_prefetch_post",
    method="POST",
    path="/api/v1/geometry/prefetch",
    request_model="PrefetchRequest",
    response_model="WarmTreeResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_PREFETCH_CANCEL: Final = Operation(
    operation_id="prefetch_cancel_api_v1_geometry_prefetch_cancel_post",
    method="POST",
    path="/api/v1/geometry/prefetch/cancel",
    request_model="WarmCancelRequest",
    response_model="WarmTreeResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_SKETCH_CHAMFER: Final = Operation(
    operation_id="sketch_chamfer_api_v1_geometry_sketch_chamfer_post",
    method="POST",
    path="/api/v1/geometry/sketch/chamfer",
    request_model="SketchChamferRequest",
    response_model="SketchCornerResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_SKETCH_EXTEND: Final = Operation(
    operation_id="sketch_extend_api_v1_geometry_sketch_extend_post",
    method="POST",
    path="/api/v1/geometry/sketch/extend",
    request_model="SketchEditRequest",
    response_model="SketchEditResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_SKETCH_FILLET: Final = Operation(
    operation_id="sketch_fillet_api_v1_geometry_sketch_fillet_post",
    method="POST",
    path="/api/v1/geometry/sketch/fillet",
    request_model="SketchFilletRequest",
    response_model="SketchCornerResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_SKETCH_MIRROR: Final = Operation(
    operation_id="sketch_mirror_api_v1_geometry_sketch_mirror_post",
    method="POST",
    path="/api/v1/geometry/sketch/mirror",
    request_model="SketchMirrorRequest",
    response_model="SketchMirrorResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_SKETCH_OFFSET: Final = Operation(
    operation_id="sketch_offset_api_v1_geometry_sketch_offset_post",
    method="POST",
    path="/api/v1/geometry/sketch/offset",
    request_model="SketchOffsetRequest",
    response_model="SketchOffsetResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_SKETCH_TRIM: Final = Operation(
    operation_id="sketch_trim_api_v1_geometry_sketch_trim_post",
    method="POST",
    path="/api/v1/geometry/sketch/trim",
    request_model="SketchEditRequest",
    response_model="SketchEditResult",
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_TESSELLATE: Final = Operation(
    operation_id="tessellate_api_v1_geometry_tessellate_post",
    method="POST",
    path="/api/v1/geometry/tessellate",
    request_model="TessellateRequest",
    response_model=None,
    path_params=(),
    required_query=(),
)

POST_GEOMETRY_TESSELLATE_META: Final = Operation(
    operation_id="tessellate_meta_api_v1_geometry_tessellate_meta_post",
    method="POST",
    path="/api/v1/geometry/tessellate/meta",
    request_model="TessellateRequest",
    response_model="TessellationMetadata",
    path_params=(),
    required_query=(),
)

GET_MATERIALS: Final = Operation(
    operation_id="list_materials_api_v1_materials_get",
    method="GET",
    path="/api/v1/materials",
    request_model=None,
    response_model="MaterialLibraryResponse",
    path_params=(),
    required_query=(),
)

GET_PARTS: Final = Operation(
    operation_id="list_parts_api_v1_parts_get",
    method="GET",
    path="/api/v1/parts",
    request_model=None,
    response_model="PartListResponse",
    path_params=(),
    required_query=(),
)

POST_PARTS: Final = Operation(
    operation_id="create_part_api_v1_parts_post",
    method="POST",
    path="/api/v1/parts",
    request_model="PartCreate",
    response_model="PartResponse",
    path_params=(),
    required_query=(),
)

GET_PARTS_PART_ID: Final = Operation(
    operation_id="get_part_api_v1_parts__part_id__get",
    method="GET",
    path="/api/v1/parts/{part_id}",
    request_model=None,
    response_model="PartResponse",
    path_params=("part_id",),
    required_query=(),
)

DELETE_PARTS_PART_ID: Final = Operation(
    operation_id="delete_part_api_v1_parts__part_id__delete",
    method="DELETE",
    path="/api/v1/parts/{part_id}",
    request_model=None,
    response_model=None,
    path_params=("part_id",),
    required_query=(),
)

PATCH_PARTS_PART_ID: Final = Operation(
    operation_id="update_part_api_v1_parts__part_id__patch",
    method="PATCH",
    path="/api/v1/parts/{part_id}",
    request_model="PartUpdate",
    response_model="PartResponse",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_DUPLICATE: Final = Operation(
    operation_id="duplicate_part_api_v1_parts__part_id__duplicate_post",
    method="POST",
    path="/api/v1/parts/{part_id}/duplicate",
    request_model=None,
    response_model="PartResponse",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_EVALUATE: Final = Operation(
    operation_id="evaluate_part_api_v1_parts__part_id__evaluate_post",
    method="POST",
    path="/api/v1/parts/{part_id}/evaluate",
    request_model=None,
    response_model="EvaluateTreeResult",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_EXPORT: Final = Operation(
    operation_id="export_part_api_v1_parts__part_id__export_post",
    method="POST",
    path="/api/v1/parts/{part_id}/export",
    request_model=None,
    response_model=None,
    path_params=("part_id",),
    required_query=("format",),
)

GET_PARTS_PART_ID_FEATURES: Final = Operation(
    operation_id="get_feature_tree_api_v1_parts__part_id__features_get",
    method="GET",
    path="/api/v1/parts/{part_id}/features",
    request_model=None,
    response_model="FeatureTreeResponse",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_FEATURES: Final = Operation(
    operation_id="create_feature_api_v1_parts__part_id__features_post",
    method="POST",
    path="/api/v1/parts/{part_id}/features",
    request_model="FeatureCreate",
    response_model="FeatureMutationResponse",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_FEATURES_IMPORT: Final = Operation(
    operation_id="import_step_api_v1_parts__part_id__features_import_post",
    method="POST",
    path="/api/v1/parts/{part_id}/features/import",
    request_model=None,
    response_model="FeatureMutationResponse",
    path_params=("part_id",),
    required_query=("expected_tree_version",),
)

PUT_PARTS_PART_ID_FEATURES_ORDER: Final = Operation(
    operation_id="reorder_features_api_v1_parts__part_id__features_order_put",
    method="PUT",
    path="/api/v1/parts/{part_id}/features/order",
    request_model="FeatureReorderRequest",
    response_model="FeatureTreeResponse",
    path_params=("part_id",),
    required_query=(),
)

GET_PARTS_PART_ID_FEATURES_FEATURE_ID: Final = Operation(
    operation_id="get_feature_api_v1_parts__part_id__features__feature_id__get",
    method="GET",
    path="/api/v1/parts/{part_id}/features/{feature_id}",
    request_model=None,
    response_model="FeatureResponse",
    path_params=("part_id", "feature_id",),
    required_query=(),
)

DELETE_PARTS_PART_ID_FEATURES_FEATURE_ID: Final = Operation(
    operation_id="delete_feature_api_v1_parts__part_id__features__feature_id__delete",
    method="DELETE",
    path="/api/v1/parts/{part_id}/features/{feature_id}",
    request_model=None,
    response_model="FeatureTreeResponse",
    path_params=("part_id", "feature_id",),
    required_query=("expected_tree_version",),
)

PATCH_PARTS_PART_ID_FEATURES_FEATURE_ID: Final = Operation(
    operation_id="update_feature_api_v1_parts__part_id__features__feature_id__patch",
    method="PATCH",
    path="/api/v1/parts/{part_id}/features/{feature_id}",
    request_model="FeatureUpdate",
    response_model="FeatureMutationResponse",
    path_params=("part_id", "feature_id",),
    required_query=(),
)

GET_PARTS_PART_ID_FEATURES_FEATURE_ID_DEPENDENTS: Final = Operation(
    operation_id="feature_dependents_api_v1_parts__part_id__features__feature_id__dependents_get",
    method="GET",
    path="/api/v1/parts/{part_id}/features/{feature_id}/dependents",
    request_model=None,
    response_model="FeatureDependents",
    path_params=("part_id", "feature_id",),
    required_query=(),
)

PATCH_PARTS_PART_ID_FEATURES_FEATURE_ID_SUPPRESS: Final = Operation(
    operation_id="suppress_feature_api_v1_parts__part_id__features__feature_id__suppress_patch",
    method="PATCH",
    path="/api/v1/parts/{part_id}/features/{feature_id}/suppress",
    request_model="FeatureSuppressRequest",
    response_model="FeatureMutationResponse",
    path_params=("part_id", "feature_id",),
    required_query=(),
)

POST_PARTS_PART_ID_FLAT_PATTERN_DXF: Final = Operation(
    operation_id="export_part_flat_pattern_api_v1_parts__part_id__flat_pattern_dxf_post",
    method="POST",
    path="/api/v1/parts/{part_id}/flat-pattern.dxf",
    request_model=None,
    response_model=None,
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_MOVE: Final = Operation(
    operation_id="move_part_api_v1_parts__part_id__move_post",
    method="POST",
    path="/api/v1/parts/{part_id}/move",
    request_model="DocumentMove",
    response_model="PartResponse",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_REDO: Final = Operation(
    operation_id="redo_part_api_v1_parts__part_id__redo_post",
    method="POST",
    path="/api/v1/parts/{part_id}/redo",
    request_model="UndoRedoRequest",
    response_model="FeatureTreeResponse",
    path_params=("part_id",),
    required_query=(),
)

PUT_PARTS_PART_ID_ROLLBACK: Final = Operation(
    operation_id="move_rollback_bar_api_v1_parts__part_id__rollback_put",
    method="PUT",
    path="/api/v1/parts/{part_id}/rollback",
    request_model="RollbackBarMove",
    response_model="FeatureTreeResponse",
    path_params=("part_id",),
    required_query=(),
)

POST_PARTS_PART_ID_UNDO: Final = Operation(
    operation_id="undo_part_api_v1_parts__part_id__undo_post",
    method="POST",
    path="/api/v1/parts/{part_id}/undo",
    request_model="UndoRedoRequest",
    response_model="FeatureTreeResponse",
    path_params=("part_id",),
    required_query=(),
)

#: Every gateway operation, keyed by its OpenAPI ``operationId``. Lets a
#: caller (and the contract-parity test) enumerate the whole surface
#: without importing each constant by name.
OPERATIONS: Final[Mapping[str, Operation]] = MappingProxyType(
    {
        "list_assemblies_api_v1_assemblies_get": GET_ASSEMBLIES,
        "create_assembly_api_v1_assemblies_post": POST_ASSEMBLIES,
        "import_assembly_step_api_v1_assemblies_import_post": POST_ASSEMBLIES_IMPORT,
        "get_assembly_api_v1_assemblies__assembly_id__get": GET_ASSEMBLIES_ASSEMBLY_ID,
        "delete_assembly_api_v1_assemblies__assembly_id__delete": DELETE_ASSEMBLIES_ASSEMBLY_ID,
        "update_assembly_api_v1_assemblies__assembly_id__patch": PATCH_ASSEMBLIES_ASSEMBLY_ID,
        "get_assembly_bom_api_v1_assemblies__assembly_id__bom_get": GET_ASSEMBLIES_ASSEMBLY_ID_BOM,
        "duplicate_assembly_api_v1_assemblies__assembly_id__duplicate_post": POST_ASSEMBLIES_ASSEMBLY_ID_DUPLICATE,
        "get_assembly_extents_api_v1_assemblies__assembly_id__extents_get": GET_ASSEMBLIES_ASSEMBLY_ID_EXTENTS,
        "create_instance_api_v1_assemblies__assembly_id__instances_post": POST_ASSEMBLIES_ASSEMBLY_ID_INSTANCES,
        "delete_instance_api_v1_assemblies__assembly_id__instances__instance_id__delete": DELETE_ASSEMBLIES_ASSEMBLY_ID_INSTANCES_INSTANCE_ID,
        "update_instance_api_v1_assemblies__assembly_id__instances__instance_id__patch": PATCH_ASSEMBLIES_ASSEMBLY_ID_INSTANCES_INSTANCE_ID,
        "create_mate_api_v1_assemblies__assembly_id__mates_post": POST_ASSEMBLIES_ASSEMBLY_ID_MATES,
        "delete_mate_api_v1_assemblies__assembly_id__mates__mate_id__delete": DELETE_ASSEMBLIES_ASSEMBLY_ID_MATES_MATE_ID,
        "move_assembly_api_v1_assemblies__assembly_id__move_post": POST_ASSEMBLIES_ASSEMBLY_ID_MOVE,
        "redo_assembly_api_v1_assemblies__assembly_id__redo_post": POST_ASSEMBLIES_ASSEMBLY_ID_REDO,
        "undo_assembly_api_v1_assemblies__assembly_id__undo_post": POST_ASSEMBLIES_ASSEMBLY_ID_UNDO,
        "login_api_v1_auth_login_post": POST_AUTH_LOGIN,
        "me_api_v1_auth_me_get": GET_AUTH_ME,
        "register_api_v1_auth_register_post": POST_AUTH_REGISTER,
        "list_drawings_api_v1_drawings_get": GET_DRAWINGS,
        "create_drawing_api_v1_drawings_post": POST_DRAWINGS,
        "get_drawing_api_v1_drawings__drawing_id__get": GET_DRAWINGS_DRAWING_ID,
        "delete_drawing_api_v1_drawings__drawing_id__delete": DELETE_DRAWINGS_DRAWING_ID,
        "update_drawing_api_v1_drawings__drawing_id__patch": PATCH_DRAWINGS_DRAWING_ID,
        "delete_annotation_api_v1_drawings__drawing_id__annotations__annotation_id__delete": DELETE_DRAWINGS_DRAWING_ID_ANNOTATIONS_ANNOTATION_ID,
        "get_drawing_bom_api_v1_drawings__drawing_id__bom_get": GET_DRAWINGS_DRAWING_ID_BOM,
        "delete_dimension_api_v1_drawings__drawing_id__dimensions__dimension_id__delete": DELETE_DRAWINGS_DRAWING_ID_DIMENSIONS_DIMENSION_ID,
        "duplicate_drawing_api_v1_drawings__drawing_id__duplicate_post": POST_DRAWINGS_DRAWING_ID_DUPLICATE,
        "export_drawing_api_v1_drawings__drawing_id__export_post": POST_DRAWINGS_DRAWING_ID_EXPORT,
        "move_drawing_api_v1_drawings__drawing_id__move_post": POST_DRAWINGS_DRAWING_ID_MOVE,
        "compose_drawing_sheet_api_v1_drawings__drawing_id__sheet_post": POST_DRAWINGS_DRAWING_ID_SHEET,
        "create_sheet_api_v1_drawings__drawing_id__sheets_post": POST_DRAWINGS_DRAWING_ID_SHEETS,
        "delete_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__delete": DELETE_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID,
        "update_sheet_api_v1_drawings__drawing_id__sheets__sheet_id__patch": PATCH_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID,
        "create_annotation_api_v1_drawings__drawing_id__sheets__sheet_id__annotations_post": POST_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID_ANNOTATIONS,
        "create_view_api_v1_drawings__drawing_id__sheets__sheet_id__views_post": POST_DRAWINGS_DRAWING_ID_SHEETS_SHEET_ID_VIEWS,
        "delete_view_api_v1_drawings__drawing_id__views__view_id__delete": DELETE_DRAWINGS_DRAWING_ID_VIEWS_VIEW_ID,
        "update_view_api_v1_drawings__drawing_id__views__view_id__patch": PATCH_DRAWINGS_DRAWING_ID_VIEWS_VIEW_ID,
        "create_dimension_api_v1_drawings__drawing_id__views__view_id__dimensions_post": POST_DRAWINGS_DRAWING_ID_VIEWS_VIEW_ID_DIMENSIONS,
        "list_folders_api_v1_folders_get": GET_FOLDERS,
        "create_folder_api_v1_folders_post": POST_FOLDERS,
        "delete_folder_api_v1_folders__folder_id__delete": DELETE_FOLDERS_FOLDER_ID,
        "rename_folder_api_v1_folders__folder_id__patch": PATCH_FOLDERS_FOLDER_ID,
        "move_folder_api_v1_folders__folder_id__move_post": POST_FOLDERS_FOLDER_ID_MOVE,
        "assembly_evaluate_api_v1_geometry_assembly_evaluate_post": POST_GEOMETRY_ASSEMBLY_EVALUATE,
        "assembly_export_api_v1_geometry_assembly_export_post": POST_GEOMETRY_ASSEMBLY_EXPORT,
        "assembly_interference_api_v1_geometry_assembly_interference_post": POST_GEOMETRY_ASSEMBLY_INTERFERENCE,
        "drawing_evaluate_api_v1_geometry_drawing_evaluate_post": POST_GEOMETRY_DRAWING_EVALUATE,
        "export_api_v1_geometry_export_post": POST_GEOMETRY_EXPORT,
        "measure_api_v1_geometry_measure_post": POST_GEOMETRY_MEASURE,
        "fetch_mesh_api_v1_geometry_meshes__mesh_glb_id__get": GET_GEOMETRY_MESHES_MESH_GLB_ID,
        "overlay_api_v1_geometry_overlay_post": POST_GEOMETRY_OVERLAY,
        "prefetch_api_v1_geometry_prefetch_post": POST_GEOMETRY_PREFETCH,
        "prefetch_cancel_api_v1_geometry_prefetch_cancel_post": POST_GEOMETRY_PREFETCH_CANCEL,
        "sketch_chamfer_api_v1_geometry_sketch_chamfer_post": POST_GEOMETRY_SKETCH_CHAMFER,
        "sketch_extend_api_v1_geometry_sketch_extend_post": POST_GEOMETRY_SKETCH_EXTEND,
        "sketch_fillet_api_v1_geometry_sketch_fillet_post": POST_GEOMETRY_SKETCH_FILLET,
        "sketch_mirror_api_v1_geometry_sketch_mirror_post": POST_GEOMETRY_SKETCH_MIRROR,
        "sketch_offset_api_v1_geometry_sketch_offset_post": POST_GEOMETRY_SKETCH_OFFSET,
        "sketch_trim_api_v1_geometry_sketch_trim_post": POST_GEOMETRY_SKETCH_TRIM,
        "tessellate_api_v1_geometry_tessellate_post": POST_GEOMETRY_TESSELLATE,
        "tessellate_meta_api_v1_geometry_tessellate_meta_post": POST_GEOMETRY_TESSELLATE_META,
        "list_materials_api_v1_materials_get": GET_MATERIALS,
        "list_parts_api_v1_parts_get": GET_PARTS,
        "create_part_api_v1_parts_post": POST_PARTS,
        "get_part_api_v1_parts__part_id__get": GET_PARTS_PART_ID,
        "delete_part_api_v1_parts__part_id__delete": DELETE_PARTS_PART_ID,
        "update_part_api_v1_parts__part_id__patch": PATCH_PARTS_PART_ID,
        "duplicate_part_api_v1_parts__part_id__duplicate_post": POST_PARTS_PART_ID_DUPLICATE,
        "evaluate_part_api_v1_parts__part_id__evaluate_post": POST_PARTS_PART_ID_EVALUATE,
        "export_part_api_v1_parts__part_id__export_post": POST_PARTS_PART_ID_EXPORT,
        "get_feature_tree_api_v1_parts__part_id__features_get": GET_PARTS_PART_ID_FEATURES,
        "create_feature_api_v1_parts__part_id__features_post": POST_PARTS_PART_ID_FEATURES,
        "import_step_api_v1_parts__part_id__features_import_post": POST_PARTS_PART_ID_FEATURES_IMPORT,
        "reorder_features_api_v1_parts__part_id__features_order_put": PUT_PARTS_PART_ID_FEATURES_ORDER,
        "get_feature_api_v1_parts__part_id__features__feature_id__get": GET_PARTS_PART_ID_FEATURES_FEATURE_ID,
        "delete_feature_api_v1_parts__part_id__features__feature_id__delete": DELETE_PARTS_PART_ID_FEATURES_FEATURE_ID,
        "update_feature_api_v1_parts__part_id__features__feature_id__patch": PATCH_PARTS_PART_ID_FEATURES_FEATURE_ID,
        "feature_dependents_api_v1_parts__part_id__features__feature_id__dependents_get": GET_PARTS_PART_ID_FEATURES_FEATURE_ID_DEPENDENTS,
        "suppress_feature_api_v1_parts__part_id__features__feature_id__suppress_patch": PATCH_PARTS_PART_ID_FEATURES_FEATURE_ID_SUPPRESS,
        "export_part_flat_pattern_api_v1_parts__part_id__flat_pattern_dxf_post": POST_PARTS_PART_ID_FLAT_PATTERN_DXF,
        "move_part_api_v1_parts__part_id__move_post": POST_PARTS_PART_ID_MOVE,
        "redo_part_api_v1_parts__part_id__redo_post": POST_PARTS_PART_ID_REDO,
        "move_rollback_bar_api_v1_parts__part_id__rollback_put": PUT_PARTS_PART_ID_ROLLBACK,
        "undo_part_api_v1_parts__part_id__undo_post": POST_PARTS_PART_ID_UNDO,
    }
)
