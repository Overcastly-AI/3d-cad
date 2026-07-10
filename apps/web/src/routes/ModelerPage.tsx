import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { tessellateBox } from "../api/tessellate";
import { InspectorPanel } from "../components/InspectorPanel";
import { TopBar } from "../components/TopBar";
import { useViewportStore } from "../store/viewport";
import { Viewport } from "../viewport/Viewport";

/** The modeler: viewport-dominant, one quiet toolbar, one inspection block. */
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
      <main className="flex min-h-0 grow flex-col md:flex-row">
        <Viewport glb={query.data?.glb} />
        <InspectorPanel
          dimensions={dimensions}
          onApply={setDimensions}
          meta={query.data?.meta}
          isFetching={query.isFetching}
          error={query.error}
        />
      </main>
    </div>
  );
}
