import { extractSseFrames, parseSseFrame, revealNextCharacter } from "./streaming";

describe("streaming helpers", () => {
  it("parses LF and CRLF server-sent event frames", () => {
    const lf = extractSseFrames("event: progress\ndata: retrieving\n\nevent: done\ndata: ok\n\n");
    expect(lf.frames).toHaveLength(2);
    expect(parseSseFrame(lf.frames[0])).toEqual({ event: "progress", data: "retrieving" });
    expect(parseSseFrame(lf.frames[1])).toEqual({ event: "done", data: "ok" });

    const crlf = extractSseFrames("event: answer_delta\r\ndata: hello\r\n\r\nrest");
    expect(crlf.frames).toHaveLength(1);
    expect(crlf.rest).toBe("rest");
    expect(parseSseFrame(crlf.frames[0])).toEqual({ event: "answer_delta", data: "hello" });
  });

  it("reveals buffered answer text one character at a time", () => {
    let visible = "";
    const buffered = "Graph RAG";

    visible = revealNextCharacter(visible, buffered);
    expect(visible).toBe("G");
    visible = revealNextCharacter(visible, buffered);
    expect(visible).toBe("Gr");

    while (visible.length < buffered.length) {
      visible = revealNextCharacter(visible, buffered);
    }

    expect(visible).toBe(buffered);
  });
});
