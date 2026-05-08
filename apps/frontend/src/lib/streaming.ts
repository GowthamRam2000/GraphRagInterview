export interface StreamEvent {
  event: string;
  data: string;
}

export function extractSseFrames(buffer: string): { frames: string[]; rest: string } {
  const frames: string[] = [];
  let rest = buffer;
  while (true) {
    const match = /\r?\n\r?\n/.exec(rest);
    if (!match) break;
    frames.push(rest.slice(0, match.index));
    rest = rest.slice(match.index + match[0].length);
  }
  return { frames, rest };
}

export function parseSseFrame(frame: string): StreamEvent | null {
  const lines = frame.split(/\r?\n/);
  const event = lines.find((line) => line.startsWith("event: "))?.slice(7) ?? "message";
  const data = lines
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6))
    .join("\n");
  if (!data) return null;
  return { event, data };
}

export function revealNextCharacter(visible: string, buffered: string): string {
  if (visible.length >= buffered.length) return visible;
  return buffered.slice(0, visible.length + 1);
}
