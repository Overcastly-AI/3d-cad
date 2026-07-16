import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { tessellateBox } from "../api/tessellate";
import { FloatingPanel } from "../components/FloatingPanel";
import { InspectorPanel } from "../components/InspectorPanel";
import { TopBar } from "../components/TopBar";
import { useViewportStore } from "../store/viewport";
import { Viewport } from "../viewport/Viewport";

/** The modeler: a full-bleed scene with one floating inspection block. */
export function ModelerPage() {
  const dimensions = useViewportStore((state) => state.dimensions);
  const setDimensions = useViewportStore((state) => state.setDimensions);

  const query = useQuery({
    queryKey: ["tessellate", "box", dimensions.x, dimensions.y, dimensions.z],
    queryFn: () => tessellateBox(dimensions),
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <main className="relative min-h-0 grow">
        <Viewport glb={query.data?.glb} />
        <FloatingPanel side="right" title="Inspector" id="inspector">
          <InspectorPanel
            dimensions={dimensions}
            onApply={setDimensions}
            meta={query.data?.meta}
            isFetching={query.isFetching}
            error={query.error}
          />
        </FloatingPanel>
      </main>
    </div>
  );
}
