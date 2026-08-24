"""Vai trò xương và bộ tự dò tên.

Retarget cần biết xương nào bên nguồn ứng với xương nào bên đích. Thay vì bắt
người dùng nối tay 20 cặp, ta quy về một bảng **vai trò** (hip, đùi, cẳng
tay...) rồi dò tên xương của từng rig về vai trò đó.

Mỗi vai trò còn khai báo vai trò **kế tiếp** trong chuỗi chi. Đó không phải
trang trí: thuật toán căn rest pose cần một vector chỉ hướng chi thật, lấy bằng
head-của-xương-này -> head-của-xương-kế-tiếp. Dùng `bone.tail` thay thế sẽ sai,
vì rig kiểu joint (Maya, game engine) có tail do Blender bịa ra.
"""

# (vai tro, vai tro ke tiep de do huong chi, co chia trai/phai khong)
ROLES = [
    ("hips",      "spine",    False),
    ("spine",     "chest",    False),
    ("chest",     "neck",     False),
    ("neck",      "head",     False),
    ("head",      None,       False),
    ("shoulder",  "upperarm", True),
    ("upperarm",  "forearm",  True),
    ("forearm",   "hand",     True),
    ("hand",      None,       True),
    ("thigh",     "shin",     True),
    ("shin",      "foot",     True),
    ("foot",      "toe",      True),
    ("toe",       None,       True),
]

ROLE_NEXT = {r: n for r, n, _ in ROLES}
ROLE_SIDED = {r: s for r, _, s in ROLES}

# Tu khoa nhan dang, xet theo thu tu — cai nao khop truoc thi lay.
# Da gom quy uoc cua Mixamo, Rigify, Unreal, va rig game kieu Maya.
KEYWORDS = {
    "hips":     ["hips", "hip", "pelvis", "root_hip", "bip01pelvis"],
    "spine":    ["spine", "spine01", "spine1", "abdomen", "waist"],
    "chest":    ["chest", "spine2", "spine02", "spine3", "spine03", "upperchest", "torso"],
    "neck":     ["neck", "neck01"],
    "head":     ["head"],
    "shoulder": ["shoulder", "clavicle", "collar"],
    "upperarm": ["upperarm", "uparm", "arm", "upperlimb", "shoulderarm"],
    "forearm":  ["forearm", "lowerarm", "elbow"],
    "hand":     ["hand", "wrist"],
    "thigh":    ["upleg", "thigh", "hip1", "leg1", "femur"],
    "shin":     ["leg", "shin", "calf", "knee", "lowerleg"],
    "foot":     ["foot", "ankle"],
    "toe":      ["toebase", "toe", "ball"],
}

# Nhung tu phai loai truoc khi so khop, neu khong "LeftForeArm" se dinh "arm".
# Thu tu xu li: dai truoc, ngan sau.
_AMBIGUOUS = ["forearm", "lowerarm", "upperarm", "uparm", "upleg", "lowerleg", "toebase"]

_SIDE_TOKENS = {
    "L": ["left", "_l", ".l", "l_", "-l", " l"],
    "R": ["right", "_r", ".r", "r_", "-r", " r"],
}


def normalize(name):
    """Bo tien to namespace va ky tu ngan cach -> chuoi thuong lien mach."""
    n = name.split(":")[-1]
    return "".join(c for c in n.lower() if c.isalnum())


def detect_side(name):
    """Tra ve 'L', 'R' hoac None."""
    raw = name.split(":")[-1].lower()
    for side, tokens in _SIDE_TOKENS.items():
        for t in tokens:
            if raw.startswith(t.strip("_.- ")) and len(raw) > 1 and not raw[1].isalpha():
                return side
            if t in ("left", "right") and t in raw:
                return side
            if raw.endswith(t) or raw.startswith(t):
                return side
    return None


def detect_role(name):
    """Doan vai tro cua mot xuong. None neu khong nhan ra."""
    n = normalize(name)
    # So khop tu dai den ngan de "forearm" khong bi "arm" nuot mat.
    best = None
    best_len = 0
    for role, words in KEYWORDS.items():
        for w in words:
            if w in n and len(w) > best_len:
                best, best_len = role, len(w)
    return best


def auto_map(armature):
    """Quet mot armature -> {(role, side): ten_xuong}.

    side la 'L'/'R' voi vai tro co chia ben, chuoi rong voi vai tro giua than.
    Xuong nao khop nhieu lan thi giu cai co ten NGAN nhat: rig hay co xuong phu
    kieu 'LeftHandThumb1' hoac 'L_Buffbone_Glb_Hand_Loc' ma ta khong muon lay.
    """
    found = {}
    for b in armature.bones:
        role = detect_role(b.name)
        if role is None:
            continue
        side = detect_side(b.name) if ROLE_SIDED[role] else ""
        if ROLE_SIDED[role] and side is None:
            continue
        key = (role, side or "")
        cur = found.get(key)
        if cur is None or len(b.name) < len(cur):
            found[key] = b.name
    return found


def pair_up(src_arm, tgt_arm):
    """Ghep hai armature -> list (role, side, ten_nguon, ten_dich).

    Chi giu cap co CA hai ben, vi mot ben thieu thi khong retarget duoc gi.
    """
    s = auto_map(src_arm)
    t = auto_map(tgt_arm)
    out = []
    for role, _, sided in ROLES:
        for side in (("L", "R") if sided else ("",)):
            key = (role, side)
            if key in s and key in t:
                out.append((role, side, s[key], t[key]))
    return out


def resolve_children(rows):
    """Bo sung xuong con dung de do huong chi cho tung cap da anh xa.

    rows: cac doi tuong co .role/.side/.src/.tgt (PropertyGroup hoac tuong tu).
    Tra ve list dict(role, side, src, tgt, src_child, tgt_child).

    Neu vai tro ke tiep khong duoc anh xa (vi du rig khong co 'neck') thi nhay
    tiep xuong vai tro sau nua, thay vi bo cuoc — 'chest' van do duoc huong nho
    'head'.
    """
    by_key = {}
    for r in rows:
        by_key[(r.role, r.side)] = r

    out = []
    for r in rows:
        child = None
        nxt = ROLE_NEXT.get(r.role)
        seen = 0
        while nxt and seen < len(ROLES):
            seen += 1
            side = r.side if ROLE_SIDED.get(nxt) else ""
            cand = by_key.get((nxt, side))
            if cand is not None:
                child = cand
                break
            nxt = ROLE_NEXT.get(nxt)
        out.append({
            "role": r.role,
            "side": r.side,
            "src": r.src,
            "tgt": r.tgt,
            "src_child": child.src if child else None,
            "tgt_child": child.tgt if child else None,
        })
    return out
