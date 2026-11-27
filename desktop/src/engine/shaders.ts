// WebGPU WGSL Ray-Traced Impostor Shaders with Screen-Space Minimum Radius Clamping + Depth Cueing

export const SPHERE_WGSL = /* wgsl */ `
struct CameraUniforms {
  view: mat4x4<f32>,
  proj: mat4x4<f32>,
  fog_params: vec4<f32>, // x = near_focus, y = depth_span, z = dark_bg (1 or 0), w = bond_radius
  viewport: vec4<f32>,   // x = width, y = height, z = min_atom_px, w = min_bond_px
};

@group(0) @binding(0) var<uniform> cam: CameraUniforms;

struct AtomInstance {
  @location(0) pos_rad: vec4<f32>,     // xyz = center, w = radius
  @location(1) color_sel: vec4<f32>,   // rgb = 0..1 color, a = >1.5 if selected else opacity
};

struct VSOut {
  @builtin(position) clip_pos: vec4<f32>,
  @location(0) center_view: vec3<f32>,
  @location(1) uv: vec2<f32>,
  @location(2) radius: f32,
  @location(3) color_sel: vec4<f32>,
};

const QUAD_CORNERS = array<vec2<f32>, 4>(
  vec2<f32>(-1.0, -1.0),
  vec2<f32>( 1.0, -1.0),
  vec2<f32>(-1.0,  1.0),
  vec2<f32>( 1.0,  1.0)
);

@vertex
fn vs_main(@builtin(vertex_index) vid: u32, inst: AtomInstance) -> VSOut {
  var out: VSOut;
  let r_raw = inst.pos_rad.w;
  if (r_raw <= 0.0001) {
    out.clip_pos = vec4<f32>(2.0, 2.0, 2.0, 1.0);
    out.radius = 0.0;
    return out;
  }
  let center_v = (cam.view * vec4<f32>(inst.pos_rad.xyz, 1.0)).xyz;
  let depth_v = max(0.25, -center_v.z);
  let px_to_world = depth_v / max(1.0, cam.viewport.y * 0.5 * cam.proj[1][1]);
  let r = max(r_raw, cam.viewport.z * px_to_world);

  let corner = QUAD_CORNERS[vid];
  let offset_v = vec3<f32>(corner * r * 1.18, 0.0);
  let pos_v = center_v + offset_v;
  out.clip_pos = cam.proj * vec4<f32>(pos_v, 1.0);
  out.center_view = center_v;
  out.uv = corner * 1.18;
  out.radius = r;
  out.color_sel = inst.color_sel;
  return out;
}

struct FSOut {
  @location(0) color: vec4<f32>,
  @builtin(frag_depth) depth: f32,
};

@fragment
fn fs_main(in: VSOut) -> FSOut {
  if (in.radius <= 0.0001) {
    discard;
  }
  let r2 = dot(in.uv, in.uv);
  if (r2 > 1.0) {
    discard;
  }
  let z_local = sqrt(max(0.0, 1.0 - r2));
  let normal = normalize(vec3<f32>(in.uv.x, in.uv.y, z_local));
  let hit_view = in.center_view + normal * in.radius;
  let clip = cam.proj * vec4<f32>(hit_view, 1.0);
  let ndc_z = clip.z / clip.w;

  let light1 = normalize(vec3<f32>(0.55, 0.72, 0.42));
  let light2 = normalize(vec3<f32>(-0.60, -0.35, 0.30));
  let view_dir = vec3<f32>(0.0, 0.0, 1.0);

  let diff1 = max(dot(normal, light1), 0.0);
  let diff2 = max(dot(normal, light2), 0.0);
  let half1 = normalize(light1 + view_dir);
  let spec = pow(max(dot(normal, half1), 0.0), 48.0);
  let fresnel = pow(1.0 - max(dot(normal, view_dir), 0.0), 3.0);

  let base_rgb = in.color_sel.rgb;
  let is_selected = in.color_sel.a > 1.5;
  var lit = base_rgb * (0.30 + 0.66 * diff1 + 0.16 * diff2) + vec3<f32>(0.40) * spec;
  lit += vec3<f32>(0.16, 0.34, 0.42) * fresnel * 0.40;

  let fog_t = clamp((-hit_view.z - cam.fog_params.x) / max(4.0, cam.fog_params.y), 0.0, 0.52);
  let bg_col = select(vec3<f32>(0.94, 0.96, 0.98), vec3<f32>(0.028, 0.044, 0.068), cam.fog_params.z > 0.5);
  lit = mix(lit, bg_col, fog_t);

  if (is_selected) {
    let rim = smoothstep(0.55, 0.98, sqrt(r2));
    lit = mix(lit, vec3<f32>(0.37, 0.92, 0.83), 0.35 + 0.65 * rim);
  }

  var out: FSOut;
  out.color = vec4<f32>(lit, min(1.0, in.color_sel.a));
  out.depth = clamp(ndc_z, 0.0, 1.0);
  return out;
}
`;

export const CYLINDER_WGSL = /* wgsl */ `
struct CameraUniforms {
  view: mat4x4<f32>,
  proj: mat4x4<f32>,
  fog_params: vec4<f32>,
  viewport: vec4<f32>, // width, height, bond_radius, min_bond_px
};

@group(0) @binding(0) var<uniform> cam: CameraUniforms;

struct BondInstance {
  @location(0) p1_r: vec4<f32>,
  @location(1) p2_unused: vec4<f32>,
  @location(2) c1: vec4<f32>,
  @location(3) c2: vec4<f32>,
};

struct VSOut {
  @builtin(position) clip_pos: vec4<f32>,
  @location(0) a_view: vec3<f32>,
  @location(1) b_view: vec3<f32>,
  @location(2) pos_view: vec3<f32>,
  @location(3) radius: f32,
  @location(4) c1: vec3<f32>,
  @location(5) c2: vec3<f32>,
};

const QUAD_BOX = array<vec2<f32>, 4>(
  vec2<f32>(0.0, -1.0),
  vec2<f32>(1.0, -1.0),
  vec2<f32>(0.0,  1.0),
  vec2<f32>(1.0,  1.0)
);

@vertex
fn vs_main(@builtin(vertex_index) vid: u32, inst: BondInstance) -> VSOut {
  var out: VSOut;
  let base_rad = cam.fog_params.w;
  if (base_rad <= 0.0001) {
    out.clip_pos = vec4<f32>(2.0, 2.0, 2.0, 1.0);
    out.radius = 0.0;
    return out;
  }
  let av = (cam.view * vec4<f32>(inst.p1_r.xyz, 1.0)).xyz;
  let bv = (cam.view * vec4<f32>(inst.p2_unused.xyz, 1.0)).xyz;
  let axis = bv - av;
  let len = length(axis);
  if (len < 0.0001) {
    out.clip_pos = vec4<f32>(2.0, 2.0, 2.0, 1.0);
    out.radius = 0.0;
    return out;
  }

  let mid_v = 0.5 * (av + bv);
  let depth_v = max(0.25, -mid_v.z);
  let px_to_world = depth_v / max(1.0, cam.viewport.y * 0.5 * cam.proj[1][1]);
  let rad = max(base_rad, cam.viewport.w * px_to_world);

  let dir = axis / len;
  let to_cam = normalize(-mid_v);
  var side = cross(dir, to_cam);
  if (length(side) < 0.001) {
    side = vec3<f32>(1.0, 0.0, 0.0);
  } else {
    side = normalize(side);
  }

  let q = QUAD_BOX[vid];
  let pad = rad * 1.45;
  let a_ext = av - dir * (rad * 0.45);
  let b_ext = bv + dir * (rad * 0.45);
  let p_v = mix(a_ext, b_ext, q.x) + side * (q.y * pad) + to_cam * pad;
  out.clip_pos = cam.proj * vec4<f32>(p_v, 1.0);
  out.a_view = av;
  out.b_view = bv;
  out.pos_view = p_v;
  out.radius = rad;
  out.c1 = inst.c1.rgb;
  out.c2 = inst.c2.rgb;
  return out;
}

struct FSOut {
  @location(0) color: vec4<f32>,
  @builtin(frag_depth) depth: f32,
};

@fragment
fn fs_main(in: VSOut) -> FSOut {
  if (in.radius <= 0.0001) {
    discard;
  }
  let ro = vec3<f32>(0.0, 0.0, 0.0);
  let rd = normalize(in.pos_view);
  let ba = in.b_view - in.a_view;
  let baba = dot(ba, ba);
  let bard = dot(ba, rd);
  let baoc = dot(ba, -in.a_view);
  let k2 = baba - bard * bard;
  let k1 = baba * dot(-in.a_view, rd) - baoc * bard;
  let k0 = baba * dot(-in.a_view, -in.a_view) - baoc * baoc - in.radius * in.radius * baba;

  let h = k1 * k1 - k2 * k0;
  if (h < 0.0 || k2 <= 1e-6) {
    discard;
  }
  let t = (-k1 - sqrt(h)) / k2;
  if (t <= 0.0) {
    discard;
  }
  let y = baoc + t * bard;
  if (y < 0.0 || y > baba) {
    discard;
  }

  let hit = ro + rd * t;
  let proj_len = y / baba;
  let normal = normalize((hit - in.a_view) - ba * proj_len);
  let clip = cam.proj * vec4<f32>(hit, 1.0);
  let ndc_z = clip.z / clip.w;

  let base_rgb = select(in.c2, in.c1, proj_len < 0.5);
  let light1 = normalize(vec3<f32>(0.55, 0.72, 0.42));
  let diff = max(dot(normal, light1), 0.0);
  let half1 = normalize(light1 - rd);
  let spec = pow(max(dot(normal, half1), 0.0), 36.0);
  var lit = base_rgb * (0.34 + 0.64 * diff) + vec3<f32>(0.24) * spec;

  let fog_t = clamp((-hit.z - cam.fog_params.x) / max(4.0, cam.fog_params.y), 0.0, 0.52);
  let bg_col = select(vec3<f32>(0.94, 0.96, 0.98), vec3<f32>(0.028, 0.044, 0.068), cam.fog_params.z > 0.5);
  lit = mix(lit, bg_col, fog_t);

  var out: FSOut;
  out.color = vec4<f32>(lit, 1.0);
  out.depth = clamp(ndc_z, 0.0, 1.0);
  return out;
}
`;

export const SURFACE_WGSL = /* wgsl */ `
struct CameraUniforms {
  view: mat4x4<f32>,
  proj: mat4x4<f32>,
  fog_params: vec4<f32>,
  viewport: vec4<f32>,
};

@group(0) @binding(0) var<uniform> cam: CameraUniforms;

struct SurfVSIn {
  @location(0) pos: vec3<f32>,
  @location(1) normal: vec3<f32>,
  @location(2) color: vec4<f32>,
};

struct SurfVSOut {
  @builtin(position) clip_pos: vec4<f32>,
  @location(0) view_pos: vec3<f32>,
  @location(1) view_normal: vec3<f32>,
  @location(2) color: vec4<f32>,
};

@vertex
fn vs_main(in: SurfVSIn) -> SurfVSOut {
  var out: SurfVSOut;
  let vp = (cam.view * vec4<f32>(in.pos, 1.0)).xyz;
  let vn = (cam.view * vec4<f32>(in.normal, 0.0)).xyz;
  out.clip_pos = cam.proj * vec4<f32>(vp, 1.0);
  out.view_pos = vp;
  out.view_normal = vn;
  out.color = in.color;
  return out;
}

@fragment
fn fs_main(in: SurfVSOut) -> @location(0) vec4<f32> {
  var n = normalize(in.view_normal);
  if (n.z < 0.0) {
    n = -n;
  }
  let light1 = normalize(vec3<f32>(0.52, 0.72, 0.45));
  let light2 = normalize(vec3<f32>(-0.55, -0.35, 0.35));
  let view_dir = vec3<f32>(0.0, 0.0, 1.0);
  let diff1 = max(dot(n, light1), 0.0);
  let diff2 = max(dot(n, light2), 0.0);
  let half1 = normalize(light1 + view_dir);
  let spec = pow(max(dot(n, half1), 0.0), 36.0);
  let fresnel = pow(1.0 - max(dot(n, view_dir), 0.0), 2.5);

  var rgb = in.color.rgb * (0.42 + 0.56 * diff1 + 0.14 * diff2) + vec3<f32>(0.24) * spec;
  rgb += vec3<f32>(0.10, 0.14, 0.18) * fresnel;
  return vec4<f32>(clamp(rgb, vec3<f32>(0.0), vec3<f32>(1.0)), in.color.a);
}
`;

export const CELL_LINE_WGSL = /* wgsl */ `
struct CameraUniforms {
  view: mat4x4<f32>,
  proj: mat4x4<f32>,
  fog_params: vec4<f32>,
  viewport: vec4<f32>,
};

@group(0) @binding(0) var<uniform> cam: CameraUniforms;

@vertex
fn vs_main(@location(0) pos: vec3<f32>) -> @builtin(position) vec4<f32> {
  return cam.proj * cam.view * vec4<f32>(pos, 1.0);
}

@fragment
fn fs_main() -> @location(0) vec4<f32> {
  return vec4<f32>(0.37, 0.92, 0.83, 0.85);
}
`;
