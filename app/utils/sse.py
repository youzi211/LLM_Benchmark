from __future__ import annotations


def parse_sse_events(raw_lines: list[str]) -> list[str]:
    events: list[str] = []
    data_lines: list[str] = []
    for raw in raw_lines:
        line = raw.rstrip("\r")
        if line == "":
            if data_lines:
                events.append("\n".join(data_lines))
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data = line[5:]
            if data.startswith(" "):
                data = data[1:]
            data_lines.append(data)
    if data_lines:
        events.append("\n".join(data_lines))
    return events
