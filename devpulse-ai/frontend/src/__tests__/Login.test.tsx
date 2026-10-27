import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Login from "../pages/Login";

describe("Login", () => {
  afterEach(() => vi.restoreAllMocks());

  it("stores the token and calls onLogin on success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ token: "abc" }), { status: 200, headers: { "content-type": "application/json" } }));
    const onLogin = vi.fn();
    render(<Login onLogin={onLogin} />);
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "segredo-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(onLogin).toHaveBeenCalled());
    expect(localStorage.getItem("devpulse.token")).toBe("abc");
  });

  it("shows the server error message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Usuário ou senha inválidos" }), { status: 401, headers: { "content-type": "application/json" } }));
    render(<Login onLogin={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "errada" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Usuário ou senha inválidos");
  });
});
