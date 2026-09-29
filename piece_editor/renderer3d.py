from __future__ import annotations

import math
from dataclasses import dataclass

import moderngl
import numpy as np

from .domain import PaletteColor, PieceDef, PieceInstance
from .mesh import load_piece_mesh
from .scene import Scene


GRID_VIEW_RADIUS = 45


VERTEX_SHADER = """
#version 330
uniform mat4 u_view_projection;
uniform mat4 u_light_view_projection;
in vec3 in_position;
in vec3 in_normal;
in vec4 in_model_0;
in vec4 in_model_1;
in vec4 in_model_2;
in vec4 in_model_3;
in vec4 in_color_selected;
out vec3 v_world_position;
out vec3 v_normal;
out vec4 v_light_space_position;
out vec3 v_color;
flat out float v_selected;
void main() {
    mat4 model = mat4(in_model_0, in_model_1, in_model_2, in_model_3);
    vec4 world = model * vec4(in_position, 1.0);
    v_world_position = world.xyz;
    v_normal = normalize(mat3(model) * in_normal);
    v_light_space_position = u_light_view_projection * world;
    v_color = in_color_selected.rgb;
    v_selected = in_color_selected.a;
    gl_Position = u_view_projection * world;
}
"""


FRAGMENT_SHADER = """
#version 330
uniform vec3 u_camera_position;
uniform vec3 u_light_direction;
uniform sampler2D u_shadow_map;
in vec3 v_world_position;
in vec3 v_normal;
in vec4 v_light_space_position;
in vec3 v_color;
flat in float v_selected;
out vec4 fragment_color;

const float PI = 3.14159265359;

float distribution_ggx(vec3 normal, vec3 halfway, float roughness) {
    float alpha = roughness * roughness;
    float alpha_squared = alpha * alpha;
    float n_dot_h = max(dot(normal, halfway), 0.0);
    float denominator = n_dot_h * n_dot_h * (alpha_squared - 1.0) + 1.0;
    return alpha_squared / max(PI * denominator * denominator, 0.0001);
}

float geometry_schlick_ggx(float n_dot_v, float roughness) {
    float radius = roughness + 1.0;
    float k = (radius * radius) / 8.0;
    return n_dot_v / max(n_dot_v * (1.0 - k) + k, 0.0001);
}

vec3 fresnel_schlick(float cosine, vec3 base_reflectance) {
    return base_reflectance + (1.0 - base_reflectance) * pow(clamp(1.0 - cosine, 0.0, 1.0), 5.0);
}

float shadow_amount(vec3 normal, vec3 light_direction) {
    vec3 projected = v_light_space_position.xyz / v_light_space_position.w;
    projected = projected * 0.5 + 0.5;
    if (projected.z > 1.0 || projected.x < 0.0 || projected.x > 1.0 || projected.y < 0.0 || projected.y > 1.0) {
        return 0.0;
    }
    float bias = max(0.0018 * (1.0 - dot(normal, light_direction)), 0.00035);
    vec2 texel = 1.0 / vec2(textureSize(u_shadow_map, 0));
    float shadow = 0.0;
    for (int x = -1; x <= 1; ++x) {
        for (int y = -1; y <= 1; ++y) {
            float closest = texture(u_shadow_map, projected.xy + vec2(x, y) * texel).r;
            shadow += projected.z - bias > closest ? 1.0 : 0.0;
        }
    }
    return shadow / 9.0;
}

vec3 aces_tone_map(vec3 color) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((color * (a * color + b)) / (color * (c * color + d) + e), 0.0, 1.0);
}

void main() {
    vec3 normal = normalize(v_normal);
    vec3 albedo = pow(v_color, vec3(2.2));
    vec3 light_direction = normalize(u_light_direction);
    vec3 view_direction = normalize(u_camera_position - v_world_position);
    vec3 half_direction = normalize(light_direction + view_direction);
    float n_dot_l = max(dot(normal, light_direction), 0.0);
    float n_dot_v = max(dot(normal, view_direction), 0.001);
    float roughness = 0.48;
    vec3 base_reflectance = vec3(0.045);
    float distribution = distribution_ggx(normal, half_direction, roughness);
    float geometry = geometry_schlick_ggx(n_dot_v, roughness) * geometry_schlick_ggx(n_dot_l, roughness);
    vec3 fresnel = fresnel_schlick(max(dot(half_direction, view_direction), 0.0), base_reflectance);
    vec3 specular = distribution * geometry * fresnel / max(4.0 * n_dot_v * n_dot_l, 0.001);
    vec3 diffuse = (vec3(1.0) - fresnel) * albedo / PI;
    float shadow = shadow_amount(normal, light_direction);
    vec3 key_light = (diffuse + specular) * n_dot_l * (1.0 - shadow * 0.78) * 2.7;

    vec3 fill_direction = normalize(vec3(0.65, 0.25, -0.55));
    float fill_diffuse = max(dot(normal, fill_direction), 0.0);
    vec3 fill_light = albedo * fill_diffuse * 0.18;
    float hemisphere = normal.y * 0.5 + 0.5;
    vec3 ambient_tint = mix(vec3(0.055, 0.045, 0.04), vec3(0.16, 0.20, 0.28), hemisphere);
    vec3 ambient = albedo * ambient_tint * 1.25;

    float rim = pow(1.0 - n_dot_v, 3.0);
    vec3 color = ambient + key_light + fill_light;
    color = mix(color, vec3(1.0, 0.68, 0.08), v_selected * (0.18 + rim * 0.7));
    float fog = smoothstep(55.0, 115.0, length(u_camera_position - v_world_position));
    color = mix(color, vec3(0.075, 0.088, 0.11), fog * 0.38);
    color = aces_tone_map(color);
    color = pow(color, vec3(1.0 / 2.2));
    fragment_color = vec4(color, 1.0);
}
"""


SIMPLE_FRAGMENT_SHADER = """
#version 330
uniform vec3 u_light_direction;
in vec3 v_normal;
in vec3 v_color;
flat in float v_selected;
out vec4 fragment_color;
void main() {
    vec3 normal = normalize(v_normal);
    float diffuse = max(dot(normal, normalize(u_light_direction)), 0.0);
    vec3 color = v_color * (0.30 + diffuse * 0.70);
    color = mix(color, vec3(1.0, 0.72, 0.12), v_selected * 0.35);
    fragment_color = vec4(color, 1.0);
}
"""


SHADOW_VERTEX_SHADER = """
#version 330
uniform mat4 u_light_view_projection;
in vec3 in_position;
in vec4 in_model_0;
in vec4 in_model_1;
in vec4 in_model_2;
in vec4 in_model_3;
void main() {
    mat4 model = mat4(in_model_0, in_model_1, in_model_2, in_model_3);
    gl_Position = u_light_view_projection * model * vec4(in_position, 1.0);
}
"""


SHADOW_FRAGMENT_SHADER = """
#version 330
void main() { }
"""


LINE_VERTEX_SHADER = """
#version 330
uniform mat4 u_view_projection;
in vec3 in_position;
in vec3 in_color;
out vec3 v_color;
void main() {
    v_color = in_color;
    gl_Position = u_view_projection * vec4(in_position, 1.0);
}
"""


LINE_FRAGMENT_SHADER = """
#version 330
in vec3 v_color;
out vec4 fragment_color;
void main() {
    fragment_color = vec4(v_color, 1.0);
}
"""


PREVIEW_VERTEX_SHADER = """
#version 330
uniform mat4 u_view_projection;
in vec3 in_position;
in vec4 in_model_0;
in vec4 in_model_1;
in vec4 in_model_2;
in vec4 in_model_3;
void main() {
    mat4 model = mat4(in_model_0, in_model_1, in_model_2, in_model_3);
    gl_Position = u_view_projection * model * vec4(in_position, 1.0);
}
"""


PREVIEW_FRAGMENT_SHADER = """
#version 330
uniform vec4 u_preview_color;
out vec4 fragment_color;
void main() {
    fragment_color = u_preview_color;
}
"""


@dataclass(slots=True)
class _GpuMesh:
    buffer: moderngl.Buffer
    source: str
    triangle_count: int
    instance_buffer: moderngl.Buffer | None = None
    instance_capacity: int = 0
    pbr_vao: moderngl.VertexArray | None = None
    simple_vao: moderngl.VertexArray | None = None
    shadow_vao: moderngl.VertexArray | None = None
    preview_buffer: moderngl.Buffer | None = None
    preview_vao: moderngl.VertexArray | None = None

    def release(self) -> None:
        for vao in (self.pbr_vao, self.simple_vao, self.shadow_vao, self.preview_vao):
            if vao:
                vao.release()
        if self.preview_buffer:
            self.preview_buffer.release()
        if self.instance_buffer:
            self.instance_buffer.release()
        self.buffer.release()


@dataclass(frozen=True, slots=True)
class RenderStats:
    source_objects: int = 0
    cached_objects: int = 0
    triangles: int = 0
    cached_triangles: int = 0
    draw_calls: int = 0


@dataclass(frozen=True, slots=True)
class RayHit:
    instance_id: str | None
    cell: tuple[int, int, int]
    normal: tuple[int, int, int]
    world_position: tuple[float, float, float]
    distance: float
    ground: bool = False


@dataclass(frozen=True, slots=True)
class RenderPreview:
    instance: PieceInstance
    color: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class _RenderBatch:
    mesh: _GpuMesh
    instance_count: int


class Camera3D:
    def __init__(self) -> None:
        self.yaw = 42.0
        self.pitch = 24.0
        self.distance = 44.0
        self.target = np.array((0.0, 10.0, 0.0), dtype=np.float32)

    @property
    def position(self) -> np.ndarray:
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        direction = np.array(
            (
                math.cos(pitch) * math.sin(yaw),
                math.sin(pitch),
                math.cos(pitch) * math.cos(yaw),
            ),
            dtype=np.float32,
        )
        return self.target + direction * self.distance

    def reset(self, scene: Scene) -> None:
        self.yaw = 42.0
        self.pitch = 24.0
        self.distance = max(scene.bounds[0], scene.bounds[1], scene.max_z - scene.min_z) * 1.5
        self.target = np.array((0.0, scene.bounds[1] * 0.34, 0.0), dtype=np.float32)

    def orbit(self, dx: float, dy: float) -> None:
        self.yaw = (self.yaw - dx * 0.22) % 360.0
        self.pitch = max(-80.0, min(80.0, self.pitch + dy * 0.18))

    def zoom(self, wheel_steps: float) -> None:
        self.distance = max(4.0, min(120.0, self.distance * math.pow(0.86, wheel_steps)))

    def pan(self, dx: float, dy: float) -> None:
        eye = self.position
        forward = _normalize(self.target - eye)
        right = _normalize(np.cross(forward, np.array((0.0, 1.0, 0.0), dtype=np.float32)))
        up = _normalize(np.cross(right, forward))
        scale = self.distance * 0.0018
        self.target += (-right * dx + up * dy) * scale


class ModernGLSceneRenderer:
    def __init__(self) -> None:
        self.context = moderngl.create_context(require=330)
        self.program = self.context.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.simple_program = self.context.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=SIMPLE_FRAGMENT_SHADER,
        )
        self.line_program = self.context.program(
            vertex_shader=LINE_VERTEX_SHADER,
            fragment_shader=LINE_FRAGMENT_SHADER,
        )
        self.preview_program = self.context.program(
            vertex_shader=PREVIEW_VERTEX_SHADER,
            fragment_shader=PREVIEW_FRAGMENT_SHADER,
        )
        self.shadow_program = self.context.program(
            vertex_shader=SHADOW_VERTEX_SHADER,
            fragment_shader=SHADOW_FRAGMENT_SHADER,
        )
        self.shadow_texture = self.context.depth_texture((2048, 2048))
        self.shadow_texture.repeat_x = False
        self.shadow_texture.repeat_y = False
        self.shadow_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.shadow_texture.compare_func = ""
        self.shadow_framebuffer = self.context.framebuffer(depth_attachment=self.shadow_texture)
        self.camera = Camera3D()
        self.meshes: dict[str, _GpuMesh] = {}
        self.mesh_signatures: dict[str, tuple[object, ...]] = {}
        self.line_buffer: moderngl.Buffer | None = None
        self.line_vao: moderngl.VertexArray | None = None
        self.line_bounds: tuple[object, ...] | None = None
        self.viewport_size = (1, 1)
        self.qt_framebuffer: moderngl.Framebuffer | None = None
        self.qt_framebuffer_id: int | None = None
        self.projection_mode = "perspective"
        self.stats = RenderStats()
        self._batch_signature: tuple[object, ...] | None = None
        self._cached_batches: tuple[_RenderBatch, ...] = ()

    def resize(self, width: int, height: int, pixel_ratio: float = 1.0) -> None:
        actual_width = max(1, round(width * pixel_ratio))
        actual_height = max(1, round(height * pixel_ratio))
        new_size = (actual_width, actual_height)
        if new_size != self.viewport_size:
            # QOpenGLWidget may resize the storage behind the same framebuffer
            # object name. A detected ModernGL framebuffer caches its original
            # dimensions, so force detection again after every physical resize.
            self.qt_framebuffer = None
            self.qt_framebuffer_id = None
        self.viewport_size = new_size
        self.context.viewport = (0, 0, actual_width, actual_height)

    def reset_camera(self, scene: Scene) -> None:
        self.camera.reset(scene)

    def render(
        self,
        scene: Scene,
        palette: tuple[PaletteColor, ...],
        selection: set[str],
        framebuffer_id: int,
        shading_mode: str = "pbr",
        preview: RenderPreview | None = None,
    ) -> None:
        batches = self._prepare_batches(scene, palette, selection)
        light_view_projection = light_view_projection_matrix(scene)
        if shading_mode == "pbr":
            self._render_shadow_map(batches, light_view_projection)
        self._bind_qt_framebuffer(framebuffer_id)
        assert self.qt_framebuffer is not None
        self.qt_framebuffer.clear(0.075, 0.088, 0.11, 1.0, depth=1.0)
        self.context.enable(moderngl.DEPTH_TEST)
        self.context.disable(moderngl.CULL_FACE)
        self._ensure_grid(scene)
        view_projection = self.view_projection()
        self.line_program["u_view_projection"].write(_gl_matrix(view_projection))
        if self.line_vao:
            self.line_vao.render(moderngl.LINES)

        light_direction = _normalize(np.array((-0.45, 0.8, 0.65), dtype=np.float32))
        if shading_mode == "simple":
            program = self.simple_program
            program["u_view_projection"].write(_gl_matrix(view_projection))
            program["u_light_direction"].value = tuple(float(v) for v in light_direction)
        else:
            program = self.program
            program["u_view_projection"].write(_gl_matrix(view_projection))
            program["u_light_view_projection"].write(_gl_matrix(light_view_projection))
            program["u_camera_position"].value = tuple(float(v) for v in self.camera.position)
            program["u_light_direction"].value = tuple(float(v) for v in light_direction)
            program["u_shadow_map"].value = 0
            self.shadow_texture.use(location=0)
        for batch in batches:
            vao = batch.mesh.simple_vao if shading_mode == "simple" else batch.mesh.pbr_vao
            assert vao is not None
            vao.render(moderngl.TRIANGLES, instances=batch.instance_count)

        if preview is not None:
            self._render_preview(scene, preview, view_projection)

        shadow_draws = len(batches) if shading_mode == "pbr" else 0
        self.stats = RenderStats(
            source_objects=len(scene.pieces),
            cached_objects=len(batches),
            triangles=sum(batch.mesh.triangle_count * batch.instance_count for batch in batches),
            cached_triangles=sum(batch.mesh.triangle_count for batch in batches),
            draw_calls=1 + len(batches) + shadow_draws + (1 if preview is not None else 0),
        )

    def _render_preview(
        self,
        scene: Scene,
        preview: RenderPreview,
        view_projection: np.ndarray,
    ) -> None:
        definition = scene.piece_defs.get(preview.instance.piece_id)
        if definition is None:
            return
        mesh = self._ensure_mesh(definition)
        if mesh.preview_buffer is None:
            mesh.preview_buffer = self.context.buffer(reserve=16 * 4, dynamic=True)
            mesh.preview_vao = self.context.vertex_array(
                self.preview_program,
                [
                    (mesh.buffer, "3f 12x", "in_position"),
                    (
                        mesh.preview_buffer,
                        "4f 4f 4f 4f /i",
                        "in_model_0",
                        "in_model_1",
                        "in_model_2",
                        "in_model_3",
                    ),
                ],
            )
        mesh.preview_buffer.write(model_matrix(preview.instance, definition).T.astype(np.float32).tobytes())
        self.preview_program["u_view_projection"].write(_gl_matrix(view_projection))
        self.preview_program["u_preview_color"].value = preview.color
        assert mesh.preview_vao is not None
        try:
            # Transparent ghosts render front faces only. This preserves the
            # translucent shell without blending rear/interior polygons
            # through the visible surface.
            self.context.cull_face = "back"
            self.context.enable(moderngl.CULL_FACE)
            self.context.enable(moderngl.BLEND)
            self.context.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
            self.context.depth_mask = False
            self.context.depth_func = "<="
            mesh.preview_vao.render(moderngl.TRIANGLES, instances=1)
        finally:
            self.context.depth_func = "<"
            self.context.depth_mask = True
            self.context.disable(moderngl.BLEND)
            self.context.disable(moderngl.CULL_FACE)

    def _render_shadow_map(
        self,
        batches: tuple[_RenderBatch, ...],
        light_view_projection: np.ndarray,
    ) -> None:
        self.shadow_framebuffer.use()
        self.context.viewport = (0, 0, *self.shadow_texture.size)
        self.shadow_framebuffer.clear(depth=1.0)
        self.context.enable(moderngl.DEPTH_TEST)
        self.shadow_program["u_light_view_projection"].write(_gl_matrix(light_view_projection))
        for batch in batches:
            assert batch.mesh.shadow_vao is not None
            batch.mesh.shadow_vao.render(moderngl.TRIANGLES, instances=batch.instance_count)

    def _prepare_batches(
        self,
        scene: Scene,
        palette: tuple[PaletteColor, ...],
        selection: set[str],
    ) -> tuple[_RenderBatch, ...]:
        grouped: dict[str, list[PieceInstance]] = {}
        for piece in scene.pieces:
            if piece.piece_id in scene.piece_defs:
                grouped.setdefault(piece.piece_id, []).append(piece)
        gpu_by_piece: dict[str, _GpuMesh] = {
            piece_id: self._ensure_mesh(scene.piece_defs[piece_id]) for piece_id in grouped
        }
        signature: tuple[object, ...] = (
            tuple((color.id, color.rgb) for color in palette),
            frozenset(selection),
            tuple(
                (
                    piece.instance_id,
                    piece.piece_id,
                    piece.position,
                    piece.rotation,
                    piece.color_id,
                )
                for piece in scene.pieces
            ),
            tuple((piece_id, self.mesh_signatures[piece_id]) for piece_id in sorted(grouped)),
        )
        if signature == self._batch_signature:
            return self._cached_batches

        colors = {color.id: _hex_rgb_float(color.rgb) for color in palette}
        batches: list[_RenderBatch] = []
        for piece_id, pieces in grouped.items():
            gpu_mesh = gpu_by_piece[piece_id]
            self._ensure_instance_capacity(gpu_mesh, len(pieces))
            instances = np.zeros((len(pieces), 20), dtype=np.float32)
            definition = scene.piece_defs[piece_id]
            for index, piece in enumerate(pieces):
                instances[index, :16] = model_matrix(piece, definition).T.reshape(16)
                instances[index, 16:19] = colors.get(piece.color_id, (0.75, 0.75, 0.75))
                instances[index, 19] = 1.0 if piece.instance_id in selection else 0.0
            assert gpu_mesh.instance_buffer is not None
            gpu_mesh.instance_buffer.write(instances.tobytes())
            batches.append(_RenderBatch(gpu_mesh, len(pieces)))
        self._batch_signature = signature
        self._cached_batches = tuple(batches)
        return self._cached_batches

    def _bind_qt_framebuffer(self, framebuffer_id: int) -> None:
        if (
            self.qt_framebuffer is None
            or self.qt_framebuffer_id != framebuffer_id
            or self.qt_framebuffer.size != self.viewport_size
        ):
            self.qt_framebuffer = self.context.detect_framebuffer(framebuffer_id)
            self.qt_framebuffer_id = framebuffer_id
        self.qt_framebuffer.use()
        width, height = self.qt_framebuffer.size
        self.viewport_size = (width, height)
        self.context.viewport = (0, 0, width, height)

    def view_projection(self) -> np.ndarray:
        width, height = self.viewport_size
        aspect = width / max(1, height)
        if self.projection_mode in {"orthographic", "iso"}:
            half_height = max(3.0, self.camera.distance * math.tan(math.radians(25.0)))
            projection = orthographic_matrix(
                -half_height * aspect,
                half_height * aspect,
                -half_height,
                half_height,
                0.1,
                300.0,
            )
        else:
            projection = perspective_matrix(50.0, aspect, 0.1, 300.0)
        view = look_at_matrix(self.camera.position, self.camera.target, np.array((0.0, 1.0, 0.0), dtype=np.float32))
        return projection @ view

    def screen_ray(self, x: float, y: float) -> tuple[np.ndarray, np.ndarray]:
        width, height = self.viewport_size
        ndc_x = 2.0 * x / max(1, width) - 1.0
        ndc_y = 1.0 - 2.0 * y / max(1, height)
        inverse = np.linalg.inv(self.view_projection())
        near = inverse @ np.array((ndc_x, ndc_y, -1.0, 1.0), dtype=np.float32)
        far = inverse @ np.array((ndc_x, ndc_y, 1.0, 1.0), dtype=np.float32)
        near = near[:3] / near[3]
        far = far[:3] / far[3]
        return near, _normalize(far - near)

    def project_world(self, point: tuple[float, float, float]) -> tuple[float, float] | None:
        clip = self.view_projection() @ np.asarray((*point, 1.0), dtype=np.float32)
        if float(clip[3]) <= 1e-8:
            return None
        ndc = clip[:3] / clip[3]
        if not np.all(np.isfinite(ndc)):
            return None
        width, height = self.viewport_size
        return (
            (float(ndc[0]) + 1.0) * 0.5 * width,
            (1.0 - float(ndc[1])) * 0.5 * height,
        )

    def raycast_grid(self, x: float, y: float, scene: Scene, include_ground: bool = True) -> RayHit | None:
        origin, direction = self.screen_ray(x, y)
        hit = _grid_raycast(origin, direction, scene)
        if hit is not None:
            return hit
        if not include_ground or abs(float(direction[1])) < 1e-8:
            return None
        distance = -float(origin[1]) / float(direction[1])
        if distance < 0.0:
            return None
        point = origin + direction * distance
        x_cell, z_cell = math.floor(float(point[0])), math.floor(float(point[2]))
        return RayHit(
            None,
            (x_cell, 0, z_cell),
            (0, 1, 0),
            tuple(float(value) for value in point),
            distance,
            True,
        )

    def pick(self, x: float, y: float, scene: Scene) -> str | None:
        hit = self.raycast_grid(x, y, scene, include_ground=False)
        return hit.instance_id if hit else None

    def _ensure_mesh(self, definition: PieceDef) -> _GpuMesh:
        path = definition.mesh_path
        signature = (
            definition.size,
            str(path) if path else None,
            path.stat().st_mtime_ns if path and path.exists() else None,
        )
        existing = self.meshes.get(definition.id)
        if existing and self.mesh_signatures.get(definition.id) == signature:
            return existing
        if existing:
            existing.release()
        mesh = load_piece_mesh(definition)
        buffer = self.context.buffer(mesh.interleaved().tobytes())
        result = _GpuMesh(buffer, mesh.source, len(mesh.positions) // 3)
        self._ensure_instance_capacity(result, 1)
        self.meshes[definition.id] = result
        self.mesh_signatures[definition.id] = signature
        self._batch_signature = None
        return result

    def _ensure_instance_capacity(self, mesh: _GpuMesh, required: int) -> None:
        if mesh.instance_buffer is not None and mesh.instance_capacity >= required:
            return
        capacity = 1
        while capacity < max(1, required):
            capacity *= 2
        for vao in (mesh.pbr_vao, mesh.simple_vao, mesh.shadow_vao):
            if vao:
                vao.release()
        if mesh.instance_buffer:
            mesh.instance_buffer.release()
        mesh.instance_buffer = self.context.buffer(reserve=capacity * 20 * 4, dynamic=True)
        mesh.instance_capacity = capacity
        instance_content = (
            mesh.instance_buffer,
            "4f 4f 4f 4f 4f /i",
            "in_model_0",
            "in_model_1",
            "in_model_2",
            "in_model_3",
            "in_color_selected",
        )
        vertex_content = (mesh.buffer, "3f 3f", "in_position", "in_normal")
        mesh.pbr_vao = self.context.vertex_array(self.program, [vertex_content, instance_content])
        mesh.simple_vao = self.context.vertex_array(self.simple_program, [vertex_content, instance_content])
        shadow_instances = (
            mesh.instance_buffer,
            "4f 4f 4f 4f 16x /i",
            "in_model_0",
            "in_model_1",
            "in_model_2",
            "in_model_3",
        )
        mesh.shadow_vao = self.context.vertex_array(
            self.shadow_program,
            [(mesh.buffer, "3f 12x", "in_position"), shadow_instances],
        )

    def _ensure_grid(self, scene: Scene) -> None:
        center = (
            math.floor(float(self.camera.target[0]) / 10.0) * 10,
            math.floor(float(self.camera.target[2]) / 10.0) * 10,
        )
        signature = (*scene.bounds, *center)
        if self.line_bounds == signature and self.line_vao is not None:
            return
        if self.line_vao:
            self.line_vao.release()
        if self.line_buffer:
            self.line_buffer.release()
        vertices = build_grid_lines(scene, center)
        self.line_buffer = self.context.buffer(vertices.tobytes())
        self.line_vao = self.context.vertex_array(
            self.line_program,
            [(self.line_buffer, "3f 3f", "in_position", "in_color")],
        )
        self.line_bounds = signature


def model_matrix(piece: PieceInstance, definition: PieceDef) -> np.ndarray:
    rotation = piece.rotation % 360
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle), math.sin(angle)
    pivot_x, _, pivot_z = definition.pivot  # type: ignore[misc]
    matrix = np.eye(4, dtype=np.float32)
    matrix[0, 0] = cosine
    matrix[0, 2] = sine
    matrix[2, 0] = -sine
    matrix[2, 2] = cosine
    matrix[0, 3] = piece.position[0] + pivot_x - (cosine * pivot_x + sine * pivot_z)
    matrix[1, 3] = piece.position[1]
    matrix[2, 3] = piece.position[2] + pivot_z - (-sine * pivot_x + cosine * pivot_z)
    return matrix


def build_grid_lines(
    scene: Scene,
    center: tuple[int, int] = (0, 0),
    radius: int = GRID_VIEW_RADIUS,
) -> np.ndarray:
    lines: list[tuple[float, float, float, float, float, float]] = []

    def add(a, b, color) -> None:
        lines.append((*a, *color))
        lines.append((*b, *color))

    grid_min_x, grid_max_x = center[0] - radius, center[0] + radius
    grid_min_z, grid_max_z = center[1] - radius, center[1] + radius
    add((0, 0, 0), (0, scene.bounds[1], 0), (0.28, 0.78, 0.4))
    floor_minor = (0.105, 0.12, 0.145)
    floor_major = (0.19, 0.22, 0.27)
    for depth in range(grid_min_z, grid_max_z + 1):
        color = floor_major if depth % 5 == 0 else floor_minor
        add((grid_min_x, 0, depth), (grid_max_x, 0, depth), color)
    for x in range(grid_min_x, grid_max_x + 1):
        color = floor_major if x % 5 == 0 else floor_minor
        add((x, 0, grid_min_z), (x, 0, grid_max_z), color)

    # Colored world axes and a subtle 30x30 Front-canvas reference border.
    add((grid_min_x, 0, 0), (grid_max_x, 0, 0), (0.78, 0.26, 0.28))
    add((0, 0, grid_min_z), (0, 0, grid_max_z), (0.28, 0.48, 0.92))
    border = (0.30, 0.34, 0.40)
    add((scene.min_x, 0.002, scene.min_z), (scene.max_x, 0.002, scene.min_z), border)
    add((scene.max_x, 0.002, scene.min_z), (scene.max_x, 0.002, scene.max_z), border)
    add((scene.max_x, 0.002, scene.max_z), (scene.min_x, 0.002, scene.max_z), border)
    add((scene.min_x, 0.002, scene.max_z), (scene.min_x, 0.002, scene.min_z), border)
    return np.asarray(lines, dtype=np.float32)


def perspective_matrix(fov_degrees: float, aspect: float, near: float, far: float) -> np.ndarray:
    scale = 1.0 / math.tan(math.radians(fov_degrees) / 2.0)
    result = np.zeros((4, 4), dtype=np.float32)
    result[0, 0] = scale / aspect
    result[1, 1] = scale
    result[2, 2] = (far + near) / (near - far)
    result[2, 3] = 2.0 * far * near / (near - far)
    result[3, 2] = -1.0
    return result


def orthographic_matrix(
    left: float,
    right: float,
    bottom: float,
    top: float,
    near: float,
    far: float,
) -> np.ndarray:
    result = np.eye(4, dtype=np.float32)
    result[0, 0] = 2.0 / (right - left)
    result[1, 1] = 2.0 / (top - bottom)
    result[2, 2] = -2.0 / (far - near)
    result[0, 3] = -(right + left) / (right - left)
    result[1, 3] = -(top + bottom) / (top - bottom)
    result[2, 3] = -(far + near) / (far - near)
    return result


def light_view_projection_matrix(scene: Scene) -> np.ndarray:
    minimum = (scene.min_x, 0, scene.min_z)
    maximum = (scene.max_x, scene.bounds[1], scene.max_z)
    if scene.occupied_bounds is not None:
        occupied_minimum, occupied_maximum = scene.occupied_bounds
        minimum = tuple(min(minimum[index], occupied_minimum[index]) for index in range(3))
        maximum = tuple(max(maximum[index], occupied_maximum[index]) for index in range(3))
    center = (np.asarray(minimum, dtype=np.float32) + np.asarray(maximum, dtype=np.float32)) * 0.5
    direction = _normalize(np.array((-0.45, 0.8, 0.65), dtype=np.float32))
    extents = tuple(maximum[index] - minimum[index] for index in range(3))
    radius = math.sqrt(sum(float(value * value) for value in extents)) * 0.58 + 3.0
    eye = center + direction * radius * 2.0
    view = look_at_matrix(eye, center, np.array((0.0, 1.0, 0.0), dtype=np.float32))
    projection = orthographic_matrix(-radius, radius, -radius, radius, 0.1, radius * 4.0)
    return projection @ view


def look_at_matrix(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    forward = _normalize(target - eye)
    side = _normalize(np.cross(forward, up))
    camera_up = np.cross(side, forward)
    result = np.eye(4, dtype=np.float32)
    result[0, :3] = side
    result[1, :3] = camera_up
    result[2, :3] = -forward
    result[0, 3] = -float(np.dot(side, eye))
    result[1, 3] = -float(np.dot(camera_up, eye))
    result[2, 3] = float(np.dot(forward, eye))
    return result


def _ray_box_distance(origin, direction, minimum, maximum) -> float | None:
    safe_direction = np.where(np.abs(direction) < 1e-8, 1e-8, direction)
    first = (minimum - origin) / safe_direction
    second = (maximum - origin) / safe_direction
    near = float(np.max(np.minimum(first, second)))
    far = float(np.min(np.maximum(first, second)))
    if far < max(near, 0.0):
        return None
    return max(near, 0.0)


def _ray_box_interval(
    origin: np.ndarray,
    direction: np.ndarray,
    minimum: np.ndarray,
    maximum: np.ndarray,
) -> tuple[float, float, tuple[int, int, int]] | None:
    near_distance = -math.inf
    far_distance = math.inf
    enter_normal = [0, 0, 0]
    for axis in range(3):
        component = float(direction[axis])
        start = float(origin[axis])
        low, high = float(minimum[axis]), float(maximum[axis])
        if abs(component) < 1e-8:
            if start < low or start > high:
                return None
            continue
        first = (low - start) / component
        second = (high - start) / component
        axis_near, axis_far = (first, second) if first <= second else (second, first)
        if axis_near > near_distance:
            near_distance = axis_near
            enter_normal = [0, 0, 0]
            enter_normal[axis] = -1 if component > 0 else 1
        far_distance = min(far_distance, axis_far)
        if near_distance > far_distance:
            return None
    if far_distance < max(near_distance, 0.0):
        return None
    return near_distance, far_distance, tuple(enter_normal)  # type: ignore[return-value]


def _grid_raycast(origin: np.ndarray, direction: np.ndarray, scene: Scene) -> RayHit | None:
    if scene.occupied_bounds is None:
        return None
    minimum = np.asarray(scene.occupied_bounds[0], dtype=np.float32)
    maximum = np.asarray(scene.occupied_bounds[1], dtype=np.float32)
    interval = _ray_box_interval(origin, direction, minimum, maximum)
    if interval is None:
        return None
    enter_distance, exit_distance, enter_normal = interval
    distance = max(0.0, enter_distance)
    point = origin + direction * (distance + 1e-5)
    point = np.minimum(np.maximum(point, minimum + 1e-6), maximum - 1e-6)
    cell = [math.floor(float(value)) for value in point]
    step = [1 if value > 1e-8 else -1 if value < -1e-8 else 0 for value in direction]
    next_crossing: list[float] = []
    crossing_delta: list[float] = []
    for axis in range(3):
        if step[axis] == 0:
            next_crossing.append(math.inf)
            crossing_delta.append(math.inf)
            continue
        boundary = cell[axis] + (1 if step[axis] > 0 else 0)
        next_crossing.append((boundary - float(origin[axis])) / float(direction[axis]))
        crossing_delta.append(abs(1.0 / float(direction[axis])))

    normal = enter_normal if enter_distance >= 0 else (0, 0, 0)
    while distance <= exit_distance + 1e-6:
        grid_cell = (cell[0], cell[1], cell[2])
        instance_id = scene.instance_id_at(grid_cell)
        if instance_id is not None:
            hit_distance = max(0.0, distance)
            hit_normal = normal
            if hit_normal == (0, 0, 0):
                cell_interval = _ray_box_interval(
                    origin,
                    direction,
                    np.asarray(grid_cell, dtype=np.float32),
                    np.asarray(grid_cell, dtype=np.float32) + 1.0,
                )
                if cell_interval is not None:
                    hit_distance = max(0.0, cell_interval[0])
                    hit_normal = cell_interval[2]
            hit_point = origin + direction * hit_distance
            return RayHit(
                instance_id,
                grid_cell,
                hit_normal,
                tuple(float(value) for value in hit_point),
                hit_distance,
                False,
            )
        axis = min(range(3), key=next_crossing.__getitem__)
        distance = next_crossing[axis]
        if not math.isfinite(distance):
            break
        cell[axis] += step[axis]
        normal_values = [0, 0, 0]
        normal_values[axis] = -step[axis]
        normal = tuple(normal_values)  # type: ignore[assignment]
        next_crossing[axis] += crossing_delta[axis]
        if not all(minimum[index] <= cell[index] < maximum[index] for index in range(3)):
            break
    return None


def _normalize(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    return vector / length if length > 1e-8 else vector


def _gl_matrix(matrix: np.ndarray) -> bytes:
    return np.asarray(matrix, dtype=np.float32).T.tobytes()


def _hex_rgb_float(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))  # type: ignore[return-value]
