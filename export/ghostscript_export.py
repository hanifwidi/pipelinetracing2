"""Compatibility entry point. SVG must first be interpreted by Inkscape."""
from export.eps_export import convert_svg_to_eps

def convert_svg_to_eps_ghostscript(svg_path, eps_path):
    return convert_svg_to_eps(svg_path, eps_path)
