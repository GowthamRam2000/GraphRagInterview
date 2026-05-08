import { render, screen } from "@testing-library/react";

import Home from "./page";

describe("Home", () => {
  it("renders the premium landing page", () => {
    render(<Home />);

    expect(screen.getByText("CognizInterview Document Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Open chat")).toBeInTheDocument();
    expect(screen.getByText("From uploaded PDF to explainable answer.")).toBeInTheDocument();
  });
});
