import pypdfium2 as pdfium
import re
from pathlib import Path
from mbft_extrator.stitching import _join_line_fragments

def agrupar_retangulos_em_linhas(rects_list, y_tolerance=3.5):
    rects_list = sorted(rects_list, key=lambda item: -item["yc"])
    lines = []
    curr = []
    curr_y = None
    for item in rects_list:
        r, yc, txt = item["rect"], item["yc"], item["txt"]
        if curr_y is None or abs(yc - curr_y) <= y_tolerance:
            curr.append((r[0], r[2], txt))
            curr_y = yc if len(curr) == 1 else (curr_y + yc) / 2
        else:
            curr.sort(key=lambda x: x[0])
            s = _join_line_fragments(curr)
            if s:
                lines.append({"y": curr_y, "text": s, "x0": curr[0][0], "x1": curr[-1][1]})
            curr = [(r[0], r[2], txt)]
            curr_y = yc
    if curr:
        curr.sort(key=lambda x: x[0])
        s = _join_line_fragments(curr)
        if s:
            lines.append({"y": curr_y, "text": s, "x0": curr[0][0], "x1": curr[-1][1]})
    return lines

def _obter_pdf_path() -> Path:
    for cand in [
        Path("data/raw/mbft.pdf"),
        Path("../data/raw/mbft.pdf"),
        Path("../../data/raw/mbft.pdf"),
        Path("mbft.pdf"),
    ]:
        if cand.exists():
            return cand
    raise FileNotFoundError("mbft.pdf não encontrado em data/raw/mbft.pdf")

doc = pdfium.PdfDocument(str(_obter_pdf_path()))
p = doc[376]
tp = p.get_textpage()

# 1. Coleta retângulos de texto
all_rects = []
for i in range(tp.count_rects()):
    r = tp.get_rect(i)
    if r[3] <= 780 and r[1] >= 30:
        txt = tp.get_text_bounded(*r).strip()
        if txt and not any(x in txt.upper() for x in ["CONSELHO NACIONAL", "MANUAL BRASILEIRO", "MBFT", "FICHA DE FISCALIZAÇÃO"]):
            if not re.match(r"^informa[cç][oõ]es\s+complementares:?$", txt, re.IGNORECASE):
                yc = (r[1] + r[3]) / 2
                xc = (r[0] + r[2]) / 2
                all_rects.append({"rect": r, "yc": yc, "xc": xc, "txt": txt, "id": i})

# Coleta imagens
images = []
for obj in p.get_objects():
    if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
        b = obj.get_bounds()
        if (b[2] - b[0]) >= 25 and (b[3] - b[1]) >= 25 and b[1] >= 30 and b[3] <= 780:
            images.append({
                "bounds": b,
                "x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3],
                "yc": (b[1] + b[3]) / 2, "xc": (b[0] + b[2]) / 2,
                "obj": obj
            })

# Acha seções agrupando em linhas
global_lines_with_rects = []
all_rects_sorted = sorted(all_rects, key=lambda item: -item["yc"])
curr = []
curr_y = None
for item in all_rects_sorted:
    r, yc, txt = item["rect"], item["yc"], item["txt"]
    if curr_y is None or abs(yc - curr_y) <= 3.5:
        curr.append(item)
        curr_y = yc if len(curr) == 1 else (curr_y + yc) / 2
    else:
        curr.sort(key=lambda x: x["rect"][0])
        s = _join_line_fragments([(it["rect"][0], it["rect"][2], it["txt"]) for it in curr])
        if s:
            global_lines_with_rects.append({"y": curr_y, "text": s, "rects": curr, "x0": curr[0]["rect"][0]})
        curr = [item]
        curr_y = yc
if curr:
    curr.sort(key=lambda x: x["rect"][0])
    s = _join_line_fragments([(it["rect"][0], it["rect"][2], it["txt"]) for it in curr])
    if s:
        global_lines_with_rects.append({"y": curr_y, "text": s, "rects": curr, "x0": curr[0]["rect"][0]})

sections = []
section_rect_ids = set()
for gl in global_lines_with_rects:
    if gl["x0"] < 60 and re.match(r"^\d+\.", gl["text"]):
        sections.append(gl)
        for r_item in gl["rects"]:
            section_rect_ids.add(r_item["id"])

print("Detected sections:")
for s in sections:
    print(f"  Y={s['y']:.1f} | {s['text']}")

# Conteúdo interno das seções (excluindo os retângulos dos títulos de seção)
internal_rects = [r for r in all_rects if r["id"] not in section_rect_ids]

section_bounds = []
for idx, s in enumerate(sections):
    y_top = s["y"]
    y_bottom = sections[idx + 1]["y"] if idx + 1 < len(sections) else 30.0
    section_bounds.append((s["text"], y_top, y_bottom))

def unificar_linhas_e_hifens(lines):
    if not lines:
        return ""
    texto = lines[0].strip()
    for l in lines[1:]:
        l = l.strip()
        if not l:
            continue
        if texto.endswith("-") and not texto.endswith(" -"):
            texto = texto[:-1] + l
        else:
            texto = texto + " " + l
    return texto

def montar_celula_html(lines, imgs, default_alt=""):
    partes = []
    
    # Se há imagem, organiza antes e depois
    if imgs:
        img = imgs[0]
        y_img = img["yc"]
        top_lines = [l for l in lines if l["y"] > y_img]
        bottom_lines = [l for l in lines if l["y"] <= y_img]
        
        # Linhas do topo (subtítulo)
        if top_lines:
            texto_top = unificar_linhas_e_hifens([l["text"] for l in top_lines])
            partes.append(f"<p><strong>{texto_top}</strong></p>")
            
        # Alt text: usa texto top ou legenda bottom
        alt = default_alt
        if top_lines:
            alt = top_lines[0]["text"]
        elif bottom_lines:
            alt = " - ".join(l["text"] for l in bottom_lines)
            
        partes.append(f'<img src="{img.get("rel_path", "")}" alt="{alt}" />')
        
        # Linhas abaixo da imagem
        if bottom_lines:
            # Se for texto descritivo longo, junta
            if len(bottom_lines) > 2 and any(len(l["text"]) > 40 for l in bottom_lines):
                texto_bot = unificar_linhas_e_hifens([l["text"] for l in bottom_lines])
                partes.append(f"<p>{texto_bot}</p>")
            else:
                for l in bottom_lines:
                    partes.append(f"<p>{l['text']}</p>")
    else:
        # Sem imagem
        texto = unificar_linhas_e_hifens([l["text"] for l in lines])
        partes.append(f"<p>{texto}</p>")
        
    return "\n".join(partes)

# Simula caminhos de imagens
img_counter = 1
for img in images:
    img["rel_path"] = f"imagens/ficha599-10_{img_counter}.png"
    img_counter += 1

html_sections = []
for title, yt, yb in section_bounds:
    sec_imgs = [img for img in images if yb <= img["yc"] <= yt]
    sec_rects = [r for r in internal_rects if yb <= r["yc"] <= yt]
    
    left_rects = [r for r in sec_rects if r["xc"] < 300]
    right_rects = [r for r in sec_rects if r["xc"] >= 300]
    left_imgs = [img for img in sec_imgs if img["xc"] < 300]
    right_imgs = [img for img in sec_imgs if img["xc"] >= 300]

    left_lines = agrupar_retangulos_em_linhas(left_rects)
    right_lines = agrupar_retangulos_em_linhas(right_rects)

def processar_pagina_ic(p, y_top_limit=780.0, codigo_ficha=""):
    tp = p.get_textpage()
    w, h = p.get_size()
    
    # 1. Coleta retângulos de texto
    all_rects = []
    for i in range(tp.count_rects()):
        r = tp.get_rect(i)
        if r[3] <= y_top_limit and r[1] >= 30:
            txt = tp.get_text_bounded(*r).strip()
            if txt and not any(x in txt.upper() for x in ["CONSELHO NACIONAL", "MANUAL BRASILEIRO", "MBFT", "FICHA DE FISCALIZAÇÃO"]):
                if not re.match(r"^informa[cç][oõ]es\s+complementares:?$", txt, re.IGNORECASE):
                    yc = (r[1] + r[3]) / 2
                    xc = (r[0] + r[2]) / 2
                    all_rects.append({"rect": r, "yc": yc, "xc": xc, "txt": txt, "id": i})

    # Coleta imagens
    images = []
    for obj in p.get_objects():
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            b = obj.get_bounds()
            if (b[2] - b[0]) >= 25 and (b[3] - b[1]) >= 25 and b[1] >= 30 and b[3] <= y_top_limit + 15:
                images.append({
                    "bounds": b,
                    "x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3],
                    "yc": (b[1] + b[3]) / 2, "xc": (b[0] + b[2]) / 2,
                    "obj": obj
                })

    # Se não há texto nem imagens, retorna vazio
    if not all_rects and not images:
        return ""

    # Acha seções agrupando em linhas
    global_lines_with_rects = []
    all_rects_sorted = sorted(all_rects, key=lambda item: -item["yc"])
    curr = []
    curr_y = None
    for item in all_rects_sorted:
        r, yc, txt = item["rect"], item["yc"], item["txt"]
        if curr_y is None or abs(yc - curr_y) <= 3.5:
            curr.append(item)
            curr_y = yc if len(curr) == 1 else (curr_y + yc) / 2
        else:
            curr.sort(key=lambda x: x["rect"][0])
            s = _join_line_fragments([(it["rect"][0], it["rect"][2], it["txt"]) for it in curr])
            if s:
                global_lines_with_rects.append({"y": curr_y, "text": s, "rects": curr, "x0": curr[0]["rect"][0]})
            curr = [item]
            curr_y = yc
    if curr:
        curr.sort(key=lambda x: x["rect"][0])
        s = _join_line_fragments([(it["rect"][0], it["rect"][2], it["txt"]) for it in curr])
        if s:
            global_lines_with_rects.append({"y": curr_y, "text": s, "rects": curr, "x0": curr[0]["rect"][0]})

    sections = []
    section_rect_ids = set()
    for gl in global_lines_with_rects:
        if gl["x0"] < 80 and re.match(r"^\d+\.", gl["text"]):
            sections.append(gl)
            for r_item in gl["rects"]:
                section_rect_ids.add(r_item["id"])

    # Se não houver seções numeradas ("1.", "2."), trata a página inteira como uma única seção
    if not sections:
        sections = [{"y": y_top_limit, "text": "", "rects": [], "x0": 0}]

    internal_rects = [r for r in all_rects if r["id"] not in section_rect_ids]

    section_bounds = []
    if sections and sections[0]["text"] and (y_top_limit - sections[0]["y"] > 25.0):
        section_bounds.append(("", y_top_limit, sections[0]["y"]))

    for idx, s in enumerate(sections):
        yt = s["y"]
        yb = sections[idx + 1]["y"] if idx + 1 < len(sections) else 30.0
        section_bounds.append((s["text"], yt, yb))

    html_sections = []
    for title, yt, yb in section_bounds:
        sec_imgs = [img for img in images if yb <= img["yc"] <= yt]
        sec_rects = [r for r in internal_rects if yb <= r["yc"] <= yt]
        
        # Imagens estritamente na coluna esquerda (x1 <= 290) ou direita (x0 >= 280)
        left_imgs = [img for img in sec_imgs if img["x1"] <= 290.0]
        right_imgs = [img for img in sec_imgs if img["x0"] >= 280.0]
        wide_imgs = [img for img in sec_imgs if img not in left_imgs and img not in right_imgs]

        left_rects = [r for r in sec_rects if r["rect"][2] <= 300.0]
        right_rects = [r for r in sec_rects if r["rect"][0] >= 280.0]

        left_lines = agrupar_retangulos_em_linhas(left_rects)
        right_lines = agrupar_retangulos_em_linhas(right_rects)

        if title:
            html_sections.append(f"<p><strong>{title}</strong></p>")
        
        # 2 colunas se houver paridade de imagens (esquerda e direita) e nenhuma imagem larga
        is_2col = (len(left_imgs) > 0 and len(right_imgs) > 0 and len(wide_imgs) == 0) or (
            len(left_imgs) == 0 and len(right_imgs) == 0 and len(wide_imgs) == 0
            and len(left_lines) > 0 and len(right_lines) > 0
            and abs(len(left_lines) - len(right_lines)) <= 4
        )
        
        if is_2col:
            td_left = montar_celula_html(left_lines, left_imgs, default_alt=f"Ilustração da Ficha {codigo_ficha}")
            td_right = montar_celula_html(right_lines, right_imgs, default_alt=f"Ilustração da Ficha {codigo_ficha}")
            tabela = (
                "<table>\n"
                "  <tr>\n"
                f"    <td>\n{td_left}\n    </td>\n"
                f"    <td>\n{td_right}\n    </td>\n"
                "  </tr>\n"
                "</table>"
            )
            html_sections.append(tabela)
        else:
            # 1 coluna linear
            all_lines = agrupar_retangulos_em_linhas(sec_rects)
            conteudo = montar_celula_html(all_lines, sec_imgs, default_alt=f"Ilustração da Ficha {codigo_ficha}")
            if conteudo:
                html_sections.append(conteudo)



    return "\n\n".join(html_sections)

# Testa na 563-00 (p. 265, index 264)
p_265 = doc[264]
print("\n--- FICHA 563-00 (P. 265) ---")
print(processar_pagina_ic(p_265, y_top_limit=450.0, codigo_ficha="563-00"))

# Testa na 683-11 (p. 632 e 633, index 631 e 632)
p_632 = doc[631]
p_633 = doc[632]
print("\n--- FICHA 683-11 (P. 632) ---")
print(processar_pagina_ic(p_632, y_top_limit=400.0, codigo_ficha="683-11"))
print("\n--- FICHA 683-11 (P. 633) ---")
print(processar_pagina_ic(p_633, y_top_limit=800.0, codigo_ficha="683-11"))



