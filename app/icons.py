"""
Ícones SVG (line icons) em um só lugar — substituem emojis na interface.
Uso no template: {{ icon('calendar', 20) }}
Todos herdam a cor via currentColor, então acompanham o texto/contexto.
"""

from markupsafe import Markup

_ICON_PATHS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.2"/><rect x="14" y="3" width="7" height="5" rx="1.2"/><rect x="14" y="12" width="7" height="9" rx="1.2"/><rect x="3" y="16" width="7" height="5" rx="1.2"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="16.5" rx="2"/><line x1="16" y1="2.5" x2="16" y2="6.5"/><line x1="8" y1="2.5" x2="8" y2="6.5"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>',
    "comb": '<rect x="3" y="6.5" width="18" height="4" rx="1"/><line x1="6" y1="10.5" x2="6" y2="15.5"/><line x1="10" y1="10.5" x2="10" y2="15.5"/><line x1="14" y1="10.5" x2="14" y2="15.5"/><line x1="18" y1="10.5" x2="18" y2="15.5"/>',
    "hand": '<path d="M7 11V6.2a1.5 1.5 0 0 1 3 0V10"/><path d="M10 10.5V4.6a1.5 1.5 0 0 1 3 0V10.5"/><path d="M13 10.5V6a1.5 1.5 0 0 1 3 0v4.6"/><path d="M16 11.5V8.4a1.5 1.5 0 0 1 3 0V15a6 6 0 0 1-6 6h-1.2a6 6 0 0 1-5-2.7L4.2 13.8a1.5 1.5 0 0 1 2.4-1.8L8 13.6"/>',
    "sparkles": '<path d="M12 3l1.7 4.6L18 9l-4.3 1.4L12 15l-1.7-4.6L6 9l4.3-1.4z"/><path d="M18.5 14l.8 2.1 2.2.8-2.2.8-.8 2.1-.8-2.1-2.2-.8 2.2-.8z"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    "heart": '<path d="M19 13.6c1.4-1.4 2.8-3.1 2.8-5.2A4.3 4.3 0 0 0 12 5.6 4.3 4.3 0 0 0 2.2 8.4c0 2.1 1.4 3.8 2.8 5.2l7 6.6z"/>',
    "tattoo": '<path d="M16.5 3a2.7 2.7 0 0 1 3.8 3.8L8 19l-5 1.5L4.5 15.5z"/><line x1="14.5" y1="5" x2="18.2" y2="8.7"/>',
    "paw": '<circle cx="6" cy="11.5" r="1.7"/><circle cx="9.7" cy="7.8" r="1.7"/><circle cx="14.3" cy="7.8" r="1.7"/><circle cx="18" cy="11.5" r="1.7"/><path d="M8.2 16.4c0-2.1 1.7-3.4 3.8-3.4s3.8 1.3 3.8 3.4c0 1.8-1.5 2.9-3.8 2.9s-3.8-1.1-3.8-2.9z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
    "ban": '<circle cx="12" cy="12" r="9"/><line x1="5.6" y1="5.6" x2="18.4" y2="18.4"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><polyline points="3.5 7.5 12 13 20.5 7.5"/>',
    "star": '<polygon points="12 2.5 14.95 8.5 21.5 9.4 16.75 14 17.9 20.5 12 17.4 6.1 20.5 7.25 14 2.5 9.4 9.05 8.5"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7.5 11 12 15.5 16.5 11"/><line x1="12" y1="15.5" x2="12" y2="3.5"/>',
    "shield": '<path d="M12 22s8-4 8-10V5.2l-8-3-8 3V12c0 6 8 10 8 10z"/>',
    "shield-check": '<path d="M12 22s8-4 8-10V5.2l-8-3-8 3V12c0 6 8 10 8 10z"/><polyline points="8.5 12 11 14.5 15.5 9.5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
    "card": '<rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    "lock": '<rect x="3.5" y="11" width="17" height="10.5" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "list": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3.2h6V4"/><line x1="8.5" y1="9" x2="15.5" y2="9"/><line x1="8.5" y1="13" x2="15.5" y2="13"/><line x1="8.5" y1="17" x2="13" y2="17"/>',
    "chart": '<path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="7" rx="0.5"/><rect x="12" y="7" width="3" height="11" rx="0.5"/><rect x="17" y="13" width="3" height="5" rx="0.5"/>',
    "trending": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "coin": '<circle cx="12" cy="12" r="9"/><path d="M15 9.3a3 3 0 0 0-3-1.4c-1.7 0-3 .9-3 2.1 0 2.9 6 1.3 6 4.2 0 1.3-1.3 2.3-3 2.3a3.2 3.2 0 0 1-3-1.5"/><line x1="12" y1="6" x2="12" y2="18"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18 2 2 0 0 0 2-2 1.5 1.5 0 0 1 1.5-1.5H18a3 3 0 0 0 3-3C21 7 16.97 3 12 3z"/><circle cx="7.5" cy="12" r="1"/><circle cx="10" cy="8" r="1"/><circle cx="14" cy="8" r="1"/><circle cx="16.5" cy="12" r="1"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="M21 15.5 16 11 6 20"/>',
    "map-pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="2.6"/>',
    "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.5-1.1a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z"/>',
    "instagram": '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="3.5"/><circle cx="17" cy="7" r="1"/>',
    "store": '<path d="M4 9.5 5.3 4h13.4L20 9.5"/><path d="M4 9.5a2.1 2.1 0 0 0 4 0 2.1 2.1 0 0 0 4 0 2.1 2.1 0 0 0 4 0 2.1 2.1 0 0 0 4 0"/><path d="M5 11v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><polyline points="8.5 12 11 14.5 15.5 9.5"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "eye-off": '<path d="M9.9 4.2A10.9 10.9 0 0 1 12 4c6.5 0 10 7 10 7a18 18 0 0 1-2.2 3.2M6.6 6.6A18 18 0 0 0 2 11s3.5 7 10 7a10.9 10.9 0 0 0 3.1-.5"/><line x1="3" y1="3" x2="21" y2="21"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><line x1="3" y1="12" x2="21" y2="12"/>',
    "clipboard-check": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3.2h6V4"/><polyline points="9 13 11 15 15 11"/>',
}


def icon(nome: str, tamanho: int = 20, stroke: float = 1.8, cls: str = "ic") -> Markup:
    """Devolve o SVG do ícone pronto para embutir no HTML."""
    corpo = _ICON_PATHS.get(nome, _ICON_PATHS["check"])
    return Markup(
        f'<svg class="{cls}" width="{tamanho}" height="{tamanho}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">{corpo}</svg>'
    )
