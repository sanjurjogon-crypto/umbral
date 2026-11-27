from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QMatrix3x3,
    QMatrix4x4,
    QOffscreenSurface,
    QOpenGLContext,
    QPainter,
    QPixmap,
    QSurfaceFormat,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
)

from .cases import CaseProfile, load_case_overlay, load_spine_texture

_VERT_SRC = """
#version 120
attribute vec3 aPos;
attribute vec3 aNormal;
attribute vec2 aTex;
uniform mat4 uMVP;
uniform mat3 uNormalMat;
varying vec3 vNormal;
varying vec2 vTex;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    vNormal = normalize(uNormalMat * aNormal);
    vTex = aTex;
}
"""

_FRAG_SRC = """
#version 120
uniform sampler2D uTex;
uniform float uShininess;
uniform float uSpecStrength;
varying vec3 vNormal;
varying vec2 vTex;
void main() {
    vec4 tex = texture2D(uTex, vTex);
    vec3 N = normalize(vNormal);
    vec3 L = normalize(vec3(0.45, 0.72, 0.90));
    vec3 V = normalize(vec3(0.0, 0.06, 1.0));
    vec3 H = normalize(L + V);

    float diff = max(dot(N, L), 0.0);
    float bounce = max(dot(N, normalize(vec3(0.0, -1.0, 0.35))), 0.0) * 0.34;
    float ambient = 0.66;
    float ndoth = dot(N, H);
    float spec = (ndoth > 0.0 ? pow(ndoth, uShininess) : 0.0) * uSpecStrength;
    float fbase = max(1.0 - max(dot(N, V), 0.0), 0.0);
    float fresnel = (fbase > 0.0 ? pow(fbase, 3.0) : 0.0) * 0.14;

    vec3 color = tex.rgb * (ambient + 0.42 * diff + bounce) + vec3(1.0, 0.98, 0.95) * (spec + fresnel);
    gl_FragColor = vec4(clamp(color, 0.0, 1.0), tex.a);
}
"""


def _mat4_perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / max(0.05, aspect)
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def _mat4_translate(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def _mat4_rotate_y(deg: float) -> np.ndarray:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    m = np.eye(4, dtype=np.float32)
    m[0, 0], m[0, 2] = c, s
    m[2, 0], m[2, 2] = -s, c
    return m


def _mat4_rotate_x(deg: float) -> np.ndarray:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    m = np.eye(4, dtype=np.float32)
    m[1, 1], m[1, 2] = c, -s
    m[2, 1], m[2, 2] = s, c
    return m


def _rounded_rect_loop(w: float, h: float, radius: float, arc_steps: int) -> list[tuple[float, float, float, float]]:
    hw, hh = w / 2.0, h / 2.0
    r = max(0.002, min(radius, hw * 0.4, hh * 0.4))
    corners = [
        (hw - r, hh - r, 0.0, math.pi / 2.0),
        (-hw + r, hh - r, math.pi / 2.0, math.pi),
        (-hw + r, -hh + r, math.pi, 1.5 * math.pi),
        (hw - r, -hh + r, 1.5 * math.pi, 2.0 * math.pi),
    ]
    pts: list[tuple[float, float, float, float]] = []
    for cx, cy, a0, a1 in corners:
        for i in range(arc_steps + 1):
            a = a0 + (a1 - a0) * (i / arc_steps)
            ca, sa = math.cos(a), math.sin(a)
            pts.append((cx + r * ca, cy + r * sa, ca, sa))
    return pts


@lru_cache(maxsize=64)
def _build_rounded_case_mesh(
    w: float,
    h: float,
    d: float,
    corner_radius: float,
    bevel: float = 0.006,
    front_uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    back_uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> dict[str, np.ndarray]:
    """Build a watertight 3D rounded-corner case mesh with continuous bevels and caps."""
    hw, hh, hd = w / 2.0, h / 2.0, d / 2.0
    b = min(bevel, corner_radius * 0.65, hd * 0.38)
    arc_steps = 8 if corner_radius >= 0.02 else 2

    outer = _rounded_rect_loop(w, h, corner_radius, arc_steps=arc_steps)
    inner = _rounded_rect_loop(
        w - 2.0 * b,
        h - 2.0 * b,
        max(0.002, corner_radius - b),
        arc_steps=arc_steps,
    )
    z_in = hd - b
    z_out = hd

    def norm3(v: tuple[float, float, float]) -> tuple[float, float, float]:
        ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
        return (v[0] / ln, v[1] / ln, v[2] / ln)

    fu0, fv0, fu1, fv1 = front_uv
    bu_a, bv_a, bu_b, bv_b = back_uv

    def uv_front(x: float, y: float) -> tuple[float, float]:
        tx = x / w + 0.5
        ty = 0.5 - y / h
        return (fu0 + tx * (fu1 - fu0), fv0 + ty * (fv1 - fv0))

    def uv_back(x: float, y: float) -> tuple[float, float]:
        tx = 0.5 - x / w
        ty = 0.5 - y / h
        return (bu_a + tx * (bu_b - bu_a), bv_a + ty * (bv_b - bv_a))

    front: list[tuple[float, ...]] = []
    back: list[tuple[float, ...]] = []
    spine: list[tuple[float, ...]] = []
    right: list[tuple[float, ...]] = []
    top_cap: list[tuple[float, ...]] = []
    bottom_cap: list[tuple[float, ...]] = []

    n_pts = len(outer)
    for i in range(n_pts):
        j = (i + 1) % n_pts
        ox0, oy0, nx0, ny0 = outer[i]
        ox1, oy1, nx1, ny1 = outer[j]
        ix0, iy0, _, _ = inner[i]
        ix1, iy1, _, _ = inner[j]

        u0, v0 = uv_front(ix0, iy0)
        u1, v1 = uv_front(ix1, iy1)
        front.extend([
            (0.0, 0.0, z_out, 0.0, 0.0, 1.0, 0.5, 0.5),
            (ix0, iy0, z_out, 0.0, 0.0, 1.0, u0, v0),
            (ix1, iy1, z_out, 0.0, 0.0, 1.0, u1, v1),
        ])
        bo_u0, bo_v0 = uv_front(ox0, oy0)
        bo_u1, bo_v1 = uv_front(ox1, oy1)
        fn0 = norm3((nx0, ny0, 1.0))
        fn1 = norm3((nx1, ny1, 1.0))
        front.extend([
            (ix0, iy0, z_out, *fn0, u0, v0),
            (ox0, oy0, z_in, *fn0, bo_u0, bo_v0),
            (ox1, oy1, z_in, *fn1, bo_u1, bo_v1),
            (ix0, iy0, z_out, *fn0, u0, v0),
            (ox1, oy1, z_in, *fn1, bo_u1, bo_v1),
            (ix1, iy1, z_out, *fn1, u1, v1),
        ])

        bu0, bv0 = uv_back(ix0, iy0)
        bu1, bv1 = uv_back(ix1, iy1)
        back.extend([
            (0.0, 0.0, -z_out, 0.0, 0.0, -1.0, 0.5, 0.5),
            (ix1, iy1, -z_out, 0.0, 0.0, -1.0, bu1, bv1),
            (ix0, iy0, -z_out, 0.0, 0.0, -1.0, bu0, bv0),
        ])
        bbo_u0, bbo_v0 = uv_back(ox0, oy0)
        bbo_u1, bbo_v1 = uv_back(ox1, oy1)
        bn0 = norm3((nx0, ny0, -1.0))
        bn1 = norm3((nx1, ny1, -1.0))
        back.extend([
            (ix0, iy0, -z_out, *bn0, bu0, bv0),
            (ox1, oy1, -z_in, *bn1, bbo_u1, bbo_v1),
            (ox0, oy0, -z_in, *bn0, bbo_u0, bbo_v0),
            (ix0, iy0, -z_out, *bn0, bu0, bv0),
            (ix1, iy1, -z_out, *bn1, bu1, bv1),
            (ox1, oy1, -z_in, *bn1, bbo_u1, bbo_v1),
        ])

        mx = 0.5 * (ox0 + ox1)
        my = 0.5 * (oy0 + oy1)
        if mx < -hw + corner_radius * 0.45 and abs(my) <= hh - corner_radius * 0.65:
            sv0 = 0.5 - oy0 / h
            sv1 = 0.5 - oy1 / h
            spine.extend([
                (ox0, oy0, -z_in, nx0, ny0, 0.0, 0.0, sv0),
                (ox0, oy0, z_in, nx0, ny0, 0.0, 1.0, sv0),
                (ox1, oy1, z_in, nx1, ny1, 0.0, 1.0, sv1),
                (ox0, oy0, -z_in, nx0, ny0, 0.0, 0.0, sv0),
                (ox1, oy1, z_in, nx1, ny1, 0.0, 1.0, sv1),
                (ox1, oy1, -z_in, nx1, ny1, 0.0, 0.0, sv1),
            ])
        elif mx > hw - corner_radius * 0.45 and abs(my) <= hh - corner_radius * 0.65:
            rv0 = 0.5 - oy0 / h
            rv1 = 0.5 - oy1 / h
            right.extend([
                (ox0, oy0, z_in, nx0, ny0, 0.0, 0.0, rv0),
                (ox0, oy0, -z_in, nx0, ny0, 0.0, 1.0, rv0),
                (ox1, oy1, -z_in, nx1, ny1, 0.0, 1.0, rv1),
                (ox0, oy0, z_in, nx0, ny0, 0.0, 0.0, rv0),
                (ox1, oy1, -z_in, nx1, ny1, 0.0, 1.0, rv1),
                (ox1, oy1, z_in, nx1, ny1, 0.0, 0.0, rv1),
            ])
        else:
            target_cap = bottom_cap if my < 0.0 else top_cap
            target_cap.extend([
                (ox0, oy0, z_in, nx0, ny0, 0.0, 0.5, 0.5),
                (ox0, oy0, -z_in, nx0, ny0, 0.0, 0.5, 0.5),
                (ox1, oy1, -z_in, nx1, ny1, 0.0, 0.5, 0.5),
                (ox0, oy0, z_in, nx0, ny0, 0.0, 0.5, 0.5),
                (ox1, oy1, -z_in, nx1, ny1, 0.0, 0.5, 0.5),
                (ox1, oy1, z_in, nx1, ny1, 0.0, 0.5, 0.5),
            ])

    return {
        "front": np.array(front, dtype=np.float32),
        "back": np.array(back, dtype=np.float32),
        "spine": np.array(spine, dtype=np.float32),
        "right": np.array(right, dtype=np.float32),
        "top_cap": np.array(top_cap, dtype=np.float32),
        "bottom_cap": np.array(bottom_cap, dtype=np.float32),
    }


@lru_cache(maxsize=64)
def _template_3d_meta(profile_key: str, shell_color: str) -> tuple[
    tuple[float, float, float, float],
    QImage,
    QImage,
    Optional[QImage],
    Optional[QImage],
]:
    """Compute tight opaque UV bounds, top/bottom cap colors, and spine/right textures."""
    tmpl = load_case_overlay(profile_key)
    if tmpl is not None:
        img = tmpl[0].toImage().convertToFormat(QImage.Format_RGBA8888)
        arr = np.frombuffer(img.bits(), dtype=np.uint8).reshape((img.height(), img.width(), 4))
        h, w = arr.shape[:2]
        xs = np.where(arr[h // 2, :, 3] > 215)[0]
        ys = np.where(arr[:, w // 2, 3] > 215)[0]
        uv = (
            (int(xs[0]) + 3) / w if len(xs) else 0.01,
            (int(ys[0]) + 3) / h if len(ys) else 0.01,
            (int(xs[-1]) - 3) / w if len(xs) else 0.99,
            (int(ys[-1]) - 3) / h if len(ys) else 0.99,
        )
        top_cap = _sample_edge_cap(arr, "top", shell_color)
        bottom_cap = _sample_edge_cap(arr, "bottom", shell_color)
    else:
        uv = (0.006, 0.006, 0.994, 0.994)
        top_cap = QImage(16, 16, QImage.Format_RGBA8888)
        top_cap.fill(QColor(shell_color))
        bottom_cap = top_cap.copy()

    sp_pix = load_spine_texture(profile_key, "left")
    spine_img = sp_pix.toImage().convertToFormat(QImage.Format_RGBA8888) if sp_pix is not None else None
    rt_pix = load_spine_texture(profile_key, "right")
    right_img = rt_pix.toImage().convertToFormat(QImage.Format_RGBA8888) if rt_pix is not None else None
    return uv, top_cap, bottom_cap, spine_img, right_img


def _sample_edge_cap(arr: np.ndarray, edge: str, fallback_hex: str) -> QImage:
    h, w = arr.shape[:2]
    strip = (
        arr[4:16, int(w * 0.12):int(w * 0.88)]
        if edge == "top"
        else arr[max(0, h - 18):max(1, h - 4), int(w * 0.12):int(w * 0.88)]
    )
    rgb = strip[:, :, :3]
    valid = rgb[(strip[:, :, 3] > 200) & (rgb.min(axis=2) < 245)]
    if len(valid) >= 12:
        med = np.median(valid, axis=0).astype(np.uint8)
        col = QColor(int(med[0]), int(med[1]), int(med[2]), 255)
    else:
        col = QColor(fallback_hex)
    cap = QImage(16, 16, QImage.Format_RGBA8888)
    cap.fill(col)
    return cap


def _procedural_spine_image(profile: CaseProfile) -> QImage:
    img = QImage(64, 512, QImage.Format_RGBA8888)
    img.fill(QColor(profile.spine_color))
    p = QPainter(img)
    p.fillRect(0, 0, 64, 56, QColor(profile.header_bg))
    p.setPen(QColor(profile.header_text))
    p.translate(32, 280)
    p.rotate(-90)
    p.drawText(-120, -12, 240, 24, Qt.AlignCenter, profile.band_label)
    p.end()
    return img.convertToFormat(QImage.Format_RGBA8888)


def _procedural_right_image(cap_img: QImage) -> QImage:
    c = cap_img.pixelColor(8, 8)
    img = QImage(32, 256, QImage.Format_RGBA8888)
    img.fill(c)
    p = QPainter(img)
    p.fillRect(9, 10, 14, 236, c.darker(120))
    p.fillRect(13, 90, 6, 76, c.darker(145))
    p.end()
    return img.convertToFormat(QImage.Format_RGBA8888)


class Case3DRenderer:
    """Offscreen MSAA OpenGL renderer for closed, beveled 3D game cases."""

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._ctx: Optional[QOpenGLContext] = None
        self._surf: Optional[QOffscreenSurface] = None
        self._prog: Optional[QOpenGLShaderProgram] = None

    def _ensure_gl(self) -> bool:
        if self._available is not None:
            return self._available
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            self._available = False
            return False
        try:
            fmt = QSurfaceFormat()
            fmt.setSamples(4)
            fmt.setDepthBufferSize(24)
            fmt.setAlphaBufferSize(8)
            ctx = QOpenGLContext()
            ctx.setFormat(fmt)
            if not ctx.create():
                self._available = False
                return False
            surf = QOffscreenSurface()
            surf.setFormat(ctx.format())
            surf.create()
            if not surf.isValid() or not ctx.makeCurrent(surf):
                self._available = False
                return False
            prog = QOpenGLShaderProgram()
            if (
                not prog.addShaderFromSourceCode(QOpenGLShader.Vertex, _VERT_SRC)
                or not prog.addShaderFromSourceCode(QOpenGLShader.Fragment, _FRAG_SRC)
                or not prog.link()
            ):
                ctx.doneCurrent()
                self._available = False
                return False
            ctx.doneCurrent()
            self._ctx = ctx
            self._surf = surf
            self._prog = prog
            self._available = True
        except Exception:  # noqa: BLE001
            self._available = False
        return self._available

    def render_case(
        self,
        profile: CaseProfile,
        front_pix: QPixmap,
        back_pix: QPixmap,
        out_w: int,
        out_h: int,
        dpr: float,
        rx: float,
        ry: float,
    ) -> Optional[QPixmap]:
        if not self._ensure_gl() or self._ctx is None or self._surf is None or self._prog is None:
            return None
        if not self._ctx.makeCurrent(self._surf):
            return None
        try:
            pw = max(64, int(round(out_w * dpr)))
            ph = max(64, int(round(out_h * dpr)))
            fbo_fmt = QOpenGLFramebufferObjectFormat()
            fbo_fmt.setAttachment(QOpenGLFramebufferObject.CombinedDepthStencil)
            fbo_fmt.setSamples(4)
            fbo = QOpenGLFramebufferObject(pw, ph, fbo_fmt)
            if not fbo.isValid():
                return None

            fbo.bind()
            gl = self._ctx.functions()
            gl.glViewport(0, 0, pw, ph)
            gl.glEnable(0x0B71)  # GL_DEPTH_TEST
            gl.glClearColor(0.0, 0.0, 0.0, 0.0)
            gl.glClear(0x4000 | 0x0100)

            uv, top_cap, bottom_cap, spine_img, right_img = _template_3d_meta(
                profile.key, profile.shell_color
            )
            front_img = front_pix.toImage().convertToFormat(QImage.Format_RGBA8888)
            back_img = back_pix.toImage().convertToFormat(QImage.Format_RGBA8888)
            if spine_img is None:
                spine_img = _procedural_spine_image(profile)
            if right_img is None:
                right_img = _procedural_right_image(top_cap)

            aspect_box = profile.w_scale / max(0.2, profile.h_scale)
            box_h = 1.18
            box_w = box_h * aspect_box
            box_d = 0.13 * max(0.65, min(1.25, profile.depth_scale))
            corner_r = (
                0.008
                if profile.shell_kind in {"cardboard", "jewel_clear"} or profile.radius <= 3.5
                else 0.036
            )
            mesh = _build_rounded_case_mesh(
                box_w, box_h, box_d, corner_radius=corner_r, bevel=0.006, front_uv=uv, back_uv=uv
            )

            proj = _mat4_perspective(26.0, pw / max(1, ph), 0.1, 30.0)
            model = _mat4_translate(0.0, 0.0, -3.55) @ _mat4_rotate_x(rx) @ _mat4_rotate_y(ry)
            mvp = proj @ model
            normal_mat = model[:3, :3]

            self._prog.bind()
            self._prog.setUniformValue("uMVP", QMatrix4x4(*mvp.flatten().tolist()))
            self._prog.setUniformValue("uNormalMat", QMatrix3x3(normal_mat.flatten().tolist()))
            self._prog.setUniformValue(self._prog.uniformLocation("uTex"), 0)
            self._prog.setUniformValue(self._prog.uniformLocation("uShininess"), 44.0)
            spec_strength = 0.12 if profile.shell_kind == "cardboard" else 0.30
            self._prog.setUniformValue(self._prog.uniformLocation("uSpecStrength"), spec_strength)

            textures = {
                "front": front_img,
                "back": back_img,
                "spine": spine_img,
                "right": right_img,
                "top_cap": top_cap,
                "bottom_cap": bottom_cap,
            }
            for face_name, verts in mesh.items():
                if len(verts) == 0:
                    continue
                tex = QOpenGLTexture(textures[face_name], QOpenGLTexture.DontGenerateMipMaps)
                tex.setMinificationFilter(QOpenGLTexture.Linear)
                tex.setMagnificationFilter(QOpenGLTexture.Linear)
                tex.setWrapMode(QOpenGLTexture.ClampToEdge)
                tex.bind(0)

                vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
                vbo.create()
                vbo.bind()
                vbo.allocate(verts.tobytes(), verts.nbytes)

                stride = 8 * 4
                pos_loc = self._prog.attributeLocation("aPos")
                norm_loc = self._prog.attributeLocation("aNormal")
                tex_loc = self._prog.attributeLocation("aTex")
                self._prog.enableAttributeArray(pos_loc)
                self._prog.enableAttributeArray(norm_loc)
                self._prog.enableAttributeArray(tex_loc)
                self._prog.setAttributeBuffer(pos_loc, 0x1406, 0, 3, stride)
                self._prog.setAttributeBuffer(norm_loc, 0x1406, 3 * 4, 3, stride)
                self._prog.setAttributeBuffer(tex_loc, 0x1406, 6 * 4, 2, stride)

                gl.glDrawArrays(0x0004, 0, int(verts.shape[0]))

                vbo.release()
                vbo.destroy()
                tex.destroy()

            self._prog.release()
            fbo.release()
            result_img = fbo.toImage()
            result_pix = QPixmap.fromImage(result_img)
            result_pix.setDevicePixelRatio(dpr)
            return result_pix
        finally:
            self._ctx.doneCurrent()


_RENDERER: Optional[Case3DRenderer] = None


def get_case_3d_renderer() -> Case3DRenderer:
    global _RENDERER
    if _RENDERER is None:
        _RENDERER = Case3DRenderer()
    return _RENDERER
