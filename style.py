# style.py
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

BACKGROUND_COLOR = "#ffffff"      # White
CARD_COLOR = "#ffffff"            # White
TEXT_COLOR = "#111827"            # Near-black
ACCENT_COLOR = "#1e3a8a"          # Navy
ACCENT_COLOR_DARK = "#0f172a"     # Navy-black

def apply_neumorphic_shadow(widget, radius=18, blur_radius=24):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setXOffset(4)
    shadow.setYOffset(4)
    shadow.setColor(QColor(17, 24, 39, 90))
    widget.setGraphicsEffect(shadow)

'''
def apply_inner_highlight(widget):
    """Apply white inner shadow on upper left for neumorphic effect."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(12)
    shadow.setXOffset(-3)
    shadow.setYOffset(-3)
    shadow.setColor(QColor(255, 255, 255, 180))
    widget.setGraphicsEffect(shadow)
    '''