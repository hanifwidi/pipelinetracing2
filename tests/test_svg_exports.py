import shutil
import re
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw
from lxml import etree
from config import cfg
from export.eps_export import convert_svg_to_eps, validate_eps
from export.svg_export import save_svg
from tracing.vtracer_wrapper import trace_image_to_svg
from tracing.svg_optimizer import optimize_svg_tree, _optimize_path_string
from tracing.merge_paths import merge_same_color_paths
from tracing.remove_duplicate_nodes import clean_duplicate_nodes
from utils.metadata_injector import inject_svg_metadata, inject_eps_metadata
from utils.quality import render_preview, inspect_svg
from utils.svg_tools import harden_for_adobe, parse_svg, SVG_NS

@pytest.mark.parametrize('size', [(512,256), (256,512), (256,256)])
def test_real_tracer_resize_and_preview_preserve_artwork(tmp_path, size):
    if not shutil.which('inkscape'):
        pytest.skip('Inkscape not installed')
    image = Image.new('RGB', size, 'white')
    ImageDraw.Draw(image).rectangle((32,32,size[0]-32,size[1]-32), fill='black')
    reference = tmp_path / 'reference.png'; image.save(reference)
    traced = trace_image_to_svg(np.asarray(image))
    svg = save_svg(harden_for_adobe(optimize_svg_tree(traced)), 'image.png', tmp_path/'final.svg')
    root = parse_svg(svg.read_bytes()).getroot()
    assert root.get('viewBox') == f'0 0 {size[0]} {size[1]}'
    assert abs(float(root.get('width'))/float(root.get('height')) - size[0]/size[1]) < .001
    preview = render_preview(svg, tmp_path/'preview.png')
    qa = inspect_svg(svg, preview, reference)
    assert qa['passed'], qa
    assert 15 <= qa['megapixels'] <= 65

@pytest.mark.parametrize('mp', [15,25,65])
def test_artboard_boundary_and_existing_viewbox(mp):
    text = '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="20" viewBox="10 20 200 100"><path d="M10 20L200 20L200 100Z"/></svg>'
    root = parse_svg(harden_for_adobe(text, mp)).getroot()
    assert root.get('viewBox') == '10 20 200 100'
    assert 15e6 <= int(root.get('width')) * int(root.get('height')) <= 65e6
    assert harden_for_adobe(harden_for_adobe(text, mp), mp) == harden_for_adobe(text, mp)

def test_optimization_preserves_scientific_numbers_and_duplicate_lines():
    assert _optimize_path_string('M1e2 1e-2L100 2.123456', 3) == 'M 100 0.01 L 100 2.123'
    root = parse_svg('<svg xmlns="http://www.w3.org/2000/svg"><path d="M1e2 0 L100 2 L100 2 l1 1 l1 1"/></svg>')
    d = clean_duplicate_nodes(root).getroot()[0].get('d')
    assert d.count('L 100 2') == 1
    assert d.count('l 1 1') == 2

def test_merge_retains_transform_and_paint_order():
    cfg.MERGE_ADJACENT_PATHS = True
    tree = parse_svg('<svg xmlns="http://www.w3.org/2000/svg"><path fill="red" transform="translate(40 0)" d="M0 0L10 0L10 10Z"/><path fill="blue" d="M0 0L10 0L10 10Z"/><path fill="red" d="M0 0L10 0L10 10Z"/></svg>')
    root = merge_same_color_paths(tree).getroot()
    assert [p.get('fill') for p in root] == ['red','blue','red']
    assert root[0].get('transform') == 'translate(40 0)'
    tree = parse_svg('<svg xmlns="http://www.w3.org/2000/svg"><path fill="red" transform="translate(40 0)" d="M0 0L10 0L10 10Z"/><path fill="red" transform="translate(40 0)" d="M20 0L30 0L30 10Z"/></svg>')
    root = merge_same_color_paths(tree).getroot()
    assert len(root) == 1 and root[0].get('transform') == 'translate(40 0)'

def test_eps_is_interpretable_and_failed_conversion_preserves_existing(tmp_path, monkeypatch):
    if not shutil.which('inkscape') or not shutil.which('gs'):
        pytest.skip('Renderers not installed')
    svg = save_svg(harden_for_adobe('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path fill="red" d="M10 10L90 10L90 90Z"/></svg>'), 'x.png', tmp_path/'x.svg')
    eps = tmp_path/'x.eps'
    assert convert_svg_to_eps(svg, eps)
    assert validate_eps(eps)
    box = re.search(rb"%%BoundingBox: ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)", eps.read_bytes())
    assert (int(box[3])-int(box[1])) * (int(box[4])-int(box[2])) >= 15_000_000
    before = eps.read_bytes()
    import export.eps_export as module
    monkeypatch.setattr(module, 'find_inkscape', lambda: '/nonexistent/inkscape')
    assert not convert_svg_to_eps(svg, eps)
    assert eps.read_bytes() == before

def test_eps_without_exiftool_never_receives_raw_xml(tmp_path, monkeypatch):
    eps = tmp_path/'x.eps'; eps.write_bytes(b'%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n')
    import utils.metadata_injector as module
    monkeypatch.setattr(module.shutil, 'which', lambda name: None)
    before = eps.read_bytes()
    assert inject_eps_metadata(eps, 'An icon', ['icon']) is False
    assert eps.read_bytes() == before

def test_svg_unicode_xmp_is_valid_and_idempotent(tmp_path):
    svg = save_svg('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path d="M0 0L1 1"/></svg>', 'x.png', tmp_path/'x.svg')
    inject_svg_metadata(svg, 'Cafe & nature', ['café', 'leaf'])
    inject_svg_metadata(svg, 'Cafe & nature', ['café', 'leaf'])
    root = parse_svg(svg.read_bytes()).getroot()
    assert len(root.findall(f'{{{SVG_NS}}}metadata')) == 1
    assert 'café' in svg.read_text()
