"""Source-backed regional grades, image names and display-only colour labels."""
import re

from .sources import CN_SKINS, key, safe_image

QUALITY = {
    "SKIN_QUALITY_EPIC": "Epic", "SKIN_QUALITY_LEGEND": "Legendary",
    "SKIN_QUALITY_OTHER": "Standard", "SKIN_QUALITY_ULTIMATE": "Ultimate",
    "SKIN_QUALITY_LIMITED": "Limited", "SKIN_QUALITY_ARCHIVE": "Archive",
}
COLORS = {
    "Aqua": ["水蓝", "#53cdd5"],
    "Black": ["黑色", "#42424a"],
    "Blue": ["蓝色", "#4a77df"],
    "Brass": ["黄铜", "#bd984b"],
    "Brown": ["棕色", "#997047"],
    "Cyan": ["青色", "#42d3d3"],
    "Emerald": ["翡翠", "#39b875"],
    "Fuchsia": ["品红", "#dc55ab"],
    "Gold": ["金色", "#d9b052"],
    "Green": ["绿色", "#68b66a"],
    "Indigo": ["靛蓝", "#6c63c8"],
    "Obsidian": ["黑曜石", "#48414b"],
    "Orange": ["橙色", "#e99848"],
    "Pearl": ["珍珠", "#e6e2d6"],
    "Pink": ["粉色", "#e681b8"],
    "Purple": ["紫色", "#a277d7"],
    "Rainbow": ["虹彩", None],
    "Red": ["红色", "#d86265"],
    "Rose": ["玫瑰", "#df7394"],
    "Ruby": ["红宝石", "#d6515a"],
    "Sapphire": ["蓝宝石", "#5677c8"],
    "Silver": ["银色", "#afb7c2"],
    "Turquoise": ["绿松石", "#54bdb0"],
    "Violet": ["紫罗兰", "#9876d4"],
    "White": ["白色", "#ececf0"],
    "Yellow": ["黄色", "#ead66a"],
    "Amber": ["琥珀", "#e0a33b"],
    "Bronze": ["青铜", "#a97a42"],
    "Burgundy": ["酒红", "#7a2135"],
    "Cobalt": ["钴蓝", "#2f5bb7"],
    "Copper": ["紫铜", "#b8733f"],
    "Coral": ["珊瑚", "#f07c6a"],
    "Crimson": ["绯红", "#c1283f"],
    "Goldstone": ["金星石", "#b7793c"],
    "Gray": ["灰色", "#8a8d93"],
    "Ice": ["冰霜", "#bfe6f2"],
    "Ivory": ["象牙白", "#f1ead6"],
    "Khaki": ["卡其", "#b8a878"],
    "Lavender": ["薰衣草", "#b7a3e0"],
    "Light Blue": [
        "浅蓝",
        "#8fc4ea"
    ],
    "Lilac": ["丁香紫", "#c3a3dc"],
    "Magenta": ["洋红", "#d0428f"],
    "Maroon": ["栗色", "#7d2f38"],
    "Mauve": ["藕荷", "#b08aa8"],
    "Midnight": ["午夜", "#2b3160"],
    "Mint": ["薄荷", "#8fd8b8"],
    "Navy": ["海军蓝", "#2b3a6b"],
    "Olive": ["橄榄", "#8c8c3c"],
    "Onyx": ["黑玛瑙", "#2f2c32"],
    "Opal": ["欧泊", "#cfe3e0"],
    "Plum": ["梅紫", "#8e4585"],
    "Scarlet": ["猩红", "#d6302f"],
    "Slate": ["石板灰", "#6d7888"],
    "Smoke": ["烟灰", "#9a9a9a"],
    "Teal": ["青绿", "#2f9e98"],
    "Vermilion": ["朱红", "#e34b2c"],
    "Ascended": ["升华", None],
    "Mythic": ["神话", None]
}


def wiki_files(champion, skin, chromas=None):
    base = f"{champion} {skin.replace(' ', '')}"
    return {
        "splash": f"File:{base}Skin WR.jpg",
        "loading": f"File:{base}Loading WR.png",
        "tile": f"File:{base}Square WR.png",
        "videoWebm": f"File:{base}Skin WR.webm",
        "videoMp4": f"File:{base}Skin WR.mp4",
        "chromas": {name: f"File:{base} ({name.replace('/', '')}) WR.png" for name in chromas or {}},
    }


def skin_metadata(entry, cn, identity, files, images):
    chromas = []
    for name, chroma in entry.get("chromas", {}).items():
        asset = images.get(files["chromas"][name], {})
        parts = [COLORS.get(part) for part in name.split("/")]
        known = all(parts)
        chromas.append({
            "id": f"{identity}:chroma:{key(name)}", "name": name,
            "nameZh": "/".join(part[0] for part in parts) if known else name,
            "colors": [part[1] for part in parts if part[1]] if known else [],
            "image": asset.get("url") if safe_image(asset.get("url")) else None,
            "sourceUrl": asset.get("descriptionurl"),
            "availability": chroma.get("availability") or None,
            "distribution": chroma.get("distribution") or None,
        })
    rarity = QUALITY.get((cn or {}).get("quality"))
    return {
        "rarity": rarity, "rarityRegion": "cn" if rarity else None,
        "raritySource": CN_SKINS if rarity else None,
        "legacy": entry.get("availability") == "Legacy",
        "availability": entry.get("availability") or None,
        "distribution": entry.get("distribution") or None,
        "regionAvailability": "cn-only" if re.search(r"\bChina\s+Exclusive\b", entry.get("distribution", ""), re.I) else "unspecified",
        "chromas": chromas,
        "chromaCoverage": "documented" if chromas else "not-documented",
    }
