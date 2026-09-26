import csv
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from config import cfg
from test_pipeline import cli
from tracing.icon_trace import IconSourceNeedsReview, trace_icon_source
from tracing.svg_optimizer import optimize_svg_tree
from tracing.remove_duplicate_nodes import clean_duplicate_nodes
from utils.adaptive_tuner import analyze_image_complexity, get_adaptive_vtracer_params
from utils.quality import inspect_svg, render_preview
from utils.svg_tools import SVG_NS, harden_for_adobe, parse_svg


def rings(two_colors=False):
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 120, 120), fill=(28, 53, 75))
    draw.ellipse((46, 46, 94, 94), fill="white")
    draw.rectangle((140, 140, 232, 232), fill=(190, 70, 25) if two_colors else (28, 53, 75))
    draw.rectangle((166, 166, 206, 206), fill="white")
    return image


def test_jpeg_edges_do_not_turn_flat_icons_into_complex_artwork():
    image = rings()
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=92)
    stream.seek(0)
    decoded = np.asarray(Image.open(stream).convert("RGB"))
    result = analyze_image_complexity(decoded)
    assert result["flat_palette"]
    assert result["color_count"] <= 3  # JPEG may add a tiny near-white cluster.
    assert sum(min(c) < 245 for c in result["palette"]) == 1
    assert result["complexity_score"] < 35
    assert result["white_background"]


@pytest.mark.parametrize("small", [False, True])
def test_gradient_is_not_flat_even_on_mostly_white_paper(small):
    image = np.full((256, 256, 3), 255, dtype=np.uint8)
    size = 64 if small else 200
    start = (256-size)//2
    gradient = np.linspace(15, 220, size, dtype=np.uint8)
    image[start:start+size, start:start+size] = np.stack([gradient, gradient//2, gradient//3], axis=1)[None]
    result = analyze_image_complexity(image)
    assert not result["flat_palette"]
    with pytest.raises(IconSourceNeedsReview, match="not reliably flat"):
        trace_icon_source(image, result, get_adaptive_vtracer_params(result))


@pytest.mark.parametrize("fill", [(230, 230, 230), (243, 243, 243)])
def test_ambiguous_pale_details_are_held_for_review(fill):
    image = rings()
    ImageDraw.Draw(image).rectangle((32, 156, 100, 220), fill=fill)
    source = np.asarray(image)
    result = analyze_image_complexity(source)
    with pytest.raises(IconSourceNeedsReview):
        trace_icon_source(source, result, get_adaptive_vtracer_params(result))


@pytest.mark.parametrize("two_colors", [False, True])
def test_binary_tracing_keeps_colored_compound_holes_after_optimization(tmp_path, two_colors):
    if not shutil.which("inkscape"):
        pytest.skip("Inkscape not installed")
    cfg.ASSET_TYPE, cfg.TARGET_MEGAPIXELS = "icon-sheet", 16
    source = rings(two_colors)
    reference = tmp_path / "reference.png"
    source.save(reference)
    analysis = analyze_image_complexity(np.asarray(source))
    svg, mask = trace_icon_source(np.asarray(source), analysis, get_adaptive_vtracer_params(analysis))
    alpha = tmp_path / "alpha.png"
    Image.fromarray(mask).save(alpha)
    optimized = clean_duplicate_nodes(optimize_svg_tree(svg))
    output = tmp_path / "output.svg"
    output.write_text(harden_for_adobe(optimized), encoding="utf-8")
    root = parse_svg(output.read_bytes()).getroot()
    paths = list(root.iter(f"{{{SVG_NS}}}path"))
    assert len(paths) == 2
    assert all(path.get("fill-rule") == "evenodd" for path in paths)
    assert len({path.get("fill") for path in paths}) == (2 if two_colors else 1)
    preview = render_preview(output, tmp_path / "preview.png")
    qa = inspect_svg(output, preview, reference, alpha)
    assert qa["passed"], qa
    assert qa["negative_space_regions"] == 3  # Outside plus each interior hole.
    assert qa["negative_space_failures"] == qa["foreground_failures"] == 0
    rendered = Image.open(preview).convert("RGBA")
    assert rendered.getpixel((280, 280))[3] == 0
    assert rendered.getpixel((744, 744))[3] == 0


@pytest.mark.parametrize("opaque_background", [False, True])
def test_white_painted_holes_fail_even_when_rgb_comparison_matches(tmp_path, opaque_background):
    if not shutil.which("inkscape"):
        pytest.skip("Inkscape not installed")
    cfg.ASSET_TYPE, cfg.TARGET_MEGAPIXELS = "icon-sheet", 16
    reference = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(reference)
    draw.rectangle((40, 40, 159, 159), fill="black")
    draw.rectangle((80, 80, 119, 119), fill="white")
    reference.save(tmp_path / "reference.png")
    Image.fromarray(np.where(np.asarray(reference)[:, :, 0] < 128, 255, 0).astype(np.uint8)).save(tmp_path / "alpha.png")
    background = '<path fill="white" d="M0 0H200V200H0Z"/>' if opaque_background else ""
    source = f'<svg xmlns="{SVG_NS}" width="200" height="200">{background}<path d="M40 40H160V160H40Z"/><path fill="white" d="M80 80H120V120H80Z"/></svg>'
    svg = tmp_path / "fake.svg"
    svg.write_text(harden_for_adobe(source), encoding="utf-8")
    preview = render_preview(svg, tmp_path / "preview.png")
    qa = inspect_svg(svg, preview, tmp_path / "reference.png", tmp_path / "alpha.png")
    assert qa["mae"] < 0.01  # The previous white-composited check would pass.
    assert not qa["passed"]
    assert qa["negative_space_failures"] == (2 if opaque_background else 1)


@pytest.mark.parametrize("size,expected", [((2048, 2048), (4000, 4000)), ((1024, 2048), (2000, 4000))])
def test_icon_artboard_has_side_limits_and_preserves_aspect(size, expected):
    source = f'<svg xmlns="{SVG_NS}" width="{size[0]}" height="{size[1]}"><path d="M0 0L1 1"/></svg>'
    result = parse_svg(harden_for_adobe(source, 16, "icon-sheet")).getroot()
    assert tuple(int(result.get(k)) for k in ("width", "height")) == expected
    assert result.get("viewBox") == f"0 0 {size[0]} {size[1]}"
    with pytest.raises(ValueError):
        harden_for_adobe(source, 25, "icon-sheet")
    with pytest.raises(ValueError):
        harden_for_adobe(source, 0.1, "icon-sheet")


def manual_csv(folder, names):
    with (folder / "manual.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Filename", "Title", "Keywords"])
        for name in names:
            writer.writerow([name, "Geometric ring shapes", "ring,geometry,shape,circle,square"])


def assets(folder):
    return list(json.loads((folder / "tracking/pipeline_manifest.json").read_text())["assets"].values())


def test_icon_profile_survives_spawn_and_rebuilds_old_or_damaged_cache(tmp_path):
    (tmp_path / "input").mkdir()
    rings().save(tmp_path / "input/a.png")
    rings(True).save(tmp_path / "input/b.png")
    manual_csv(tmp_path, ("a.png", "b.png"))
    args = ("--workers", "2", "--metadata-csv", "manual.csv", "--no-archive")
    before = cli(tmp_path, *args)
    assert before.returncode == 0, before.stdout + before.stderr
    old_signatures = {a["signature"] for a in assets(tmp_path)}
    for repeat in range(3):
        result = cli(tmp_path, *args, "--asset-type", "icon-sheet")
        assert result.returncode == 0, result.stdout + result.stderr
        records = assets(tmp_path)
        assert all(a["status"] == "ready" and a["asset_type"] == "icon-sheet" for a in records)
        assert all(a["quality"]["transparency_checked"] and a["quality"]["width"] == 4000 for a in records)
        assert not old_signatures.intersection(a["signature"] for a in records)
        assert all(a["trace_cache_hit"] == (repeat == 1) for a in records)
        if repeat == 1:
            Path(records[0]["alpha_reference"]).unlink()
            (Path(records[1]["reference"]).parent / "analysis.json").write_text("{broken")
    assert len(list((tmp_path / "input").glob("*.png"))) == 2


def test_nonwhite_icon_source_is_held_without_archiving_or_ready_csv(tmp_path):
    (tmp_path / "input").mkdir()
    image = Image.new("RGB", (256, 256), "#e0d0b0")
    ImageDraw.Draw(image).ellipse((40, 40, 210, 210), fill="#203040")
    image.save(tmp_path / "input/asset.png")
    manual_csv(tmp_path, ("asset.png",))
    result = cli(tmp_path, "--workers", "1", "--asset-type", "icon-sheet", "--metadata-csv", "manual.csv")
    assert result.returncode == 0, result.stdout + result.stderr
    asset = assets(tmp_path)[0]
    assert asset["status"] == "needs_review"
    assert any("plain white background" in warning for warning in asset["quality"]["warnings"])
    assert (tmp_path / "input/asset.png").exists()
    assert not (tmp_path / "output_svg/metadata.csv").exists()
