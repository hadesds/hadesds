import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../components/StatusBadge";

it("renders a translated label with tone class", () => {
  render(<StatusBadge status="sent" />);
  const el = screen.getByText("Aceita pelo provedor");
  expect(el).toHaveClass("badge-ok");
});
