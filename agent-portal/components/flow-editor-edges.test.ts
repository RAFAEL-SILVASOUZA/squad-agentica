import { describe, it, expect } from "vitest";
import { flowEdgesToPipelineEdges, pipelineToFlowEdges } from "./FlowEditor";
import type { Pipeline } from "@/lib/types";

describe("conversão de arestas do editor", () => {
  it("preserva canal e mensagem da aprovação ao recarregar e salvar", () => {
    const pipeline = {
      edges: [
        {
          id: "e1",
          type: "data",
          source: "a",
          target: "b",
          requiresApproval: true,
          approvalChannel: "in-app",
          approvalMessage: "Revise a especificação",
          dataMapping: { sourceOutput: "spec", targetInput: "spec" },
        },
      ],
    } as unknown as Pipeline;
    const [edge] = flowEdgesToPipelineEdges(pipelineToFlowEdges(pipeline));
    expect(edge.approvalMessage).toBe("Revise a especificação");
    expect(edge.approvalChannel).toBe("in-app");
    expect(edge.requiresApproval).toBe(true);
  });
});
