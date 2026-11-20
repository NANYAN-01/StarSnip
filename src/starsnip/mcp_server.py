"""Optional MCP server (requires mcp<2): expose screen capture + OCR to agents."""

from mcp.server.fastmcp import FastMCP

from . import capture, config, ocr_core

mcp = FastMCP("starsnip")


@mcp.tool()
def screen_capture_ocr(region: str = "", prompt: str = "", model: str = "") -> str:
    """Capture the screen (or a region) and OCR it with the configured vision model.

    Args:
        region: "x,y,w,h" in screen coordinates; empty = whole virtual screen.
        prompt: optional OCR instruction override.
        model: optional model override.
    """
    cfg = config.load()
    capture.enable_dpi_awareness()
    img = capture.capture_screen()
    if region:
        x, y, w, h = [int(v) for v in region.replace(" ", "").split(",")]
        img = img.crop(x - img.origin[0], y - img.origin[1], w, h)
    png = img.to_png_scaled(int(cfg.get("max_side_px", 1280)))
    result = ocr_core.call(
        png, model or cfg["default_model"], cfg["ollama_url"],
        prompt=prompt or cfg.get("prompt", ocr_core.DEFAULT_PROMPT),
        timeout=float(cfg.get("timeout_s", 60)))
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "OCR failed")
    return result["text"]


def run() -> None:
    mcp.run(transport="stdio")
