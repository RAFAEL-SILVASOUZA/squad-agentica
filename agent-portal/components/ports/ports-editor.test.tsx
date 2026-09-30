import * as React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PortsEditor, type Port } from "./ports-editor";

function AddWrapper({ onChangeSpy }: { onChangeSpy: (p: Port[]) => void }) {
  const [ports, setPorts] = React.useState<Port[]>([]);
  const handleChange = (p: Port[]) => {
    setPorts(p);
    onChangeSpy(p);
  };
  return <PortsEditor label="Entradas" value={ports} onChange={handleChange} types={["string"]} />;
}

describe("PortsEditor", () => {
  it("adicionar duas linhas chama onChange com dois ports", () => {
    const onChange = vi.fn();
    render(<AddWrapper onChangeSpy={onChange} />);
    fireEvent.click(screen.getByText("+ Adicionar"));
    fireEvent.click(screen.getByText("+ Adicionar"));
    expect(onChange).toHaveBeenLastCalledWith([
      { name: "", type: "string", required: false },
      { name: "", type: "string", required: false },
    ]);
  });

  it("nome duplicado mostra 'Nome repetido' e não chama onChange", () => {
    const onChange = vi.fn();
    const value: Port[] = [
      { name: "foo", type: "string", required: false },
      { name: "bar", type: "string", required: false },
    ];
    render(<PortsEditor label="Entradas" value={value} onChange={onChange} types={["string"]} />);
    fireEvent.change(screen.getByLabelText("Nome do port 2"), { target: { value: "foo" } });
    expect(screen.getByText("Nome repetido")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("'Ver JSON' mostra o JSON com description", () => {
    const onChange = vi.fn();
    const value: Port[] = [{ name: "input", type: "string", required: true, description: "A description" }];
    render(<PortsEditor label="Entradas" value={value} onChange={onChange} types={["string"]} />);
    fireEvent.click(screen.getByText("Ver JSON"));
    expect(screen.getByText(/"description": "A description"/)).toBeInTheDocument();
  });
});
