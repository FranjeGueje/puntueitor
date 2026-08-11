"""
Fondo de pantalla: la carátula del juego seleccionado, desenfocada y
oscurecida, ajustada para llenar la pantalla a los lados sin deformarse
(equivalente a `background-size: cover` en CSS) y con un ligero acercamiento,
para que no compita con las cajas del carrusel ni con el texto.

El tamaño de la card se recalcula en cada evento de ventana, no solo al
arrancar: Panda3D ajusta el FOV horizontal de la cámara automáticamente al
cambiar el tamaño de la ventana (aspect ratio más ancho → más FOV
horizontal, FOV vertical fijo — comprobado en runtime), así que una card
dimensionada una sola vez al inicio se queda corta y deja bordes negros a
los lados al maximizar a un aspect ratio más ancho que el de arranque.
"""
import math

from panda3d.core import CardMaker, NodePath, PNMImage, Texture, TextureStage

ZOOM = 1.15  # >1 = acerca la imagen (recorta un poco el centro y lo amplía)

# Cuánto se oscurece la imagen de fondo, 0 = intacta, 1 = negra.
#
# Se aplica con `set_color_scale` sobre la propia card, NO con una segunda
# card negra semitransparente por delante (que es como estaba, y no
# funcionaba). El resultado es idéntico píxel a píxel — componer negro con
# alfa `a` sobre la imagen da `img*(1-a) + 0*a` = `img*(1-a)`, exactamente lo
# que hace multiplicar por `1-a` — pero sin depender del orden de dibujado.
# La card del velo estaba EXACTAMENTE en la misma posición y escala que la de
# la imagen: dos superficies coplanares con el mismo valor de profundidad, y
# el test de profundidad por defecto en Panda3D es `menor que` (no `menor o
# igual`), así que el velo perdía contra la imagen y se descartaba entero. De
# ahí que el fondo saliera a plena luz por mucho que se subiera el alfa.
DARKEN = 0.78

# La carátula de IGDB es pequeña (unos 264x374) y aquí se estira a pantalla
# completa: aumentada ~7x se ven los píxeles y los bloques del JPEG. Se
# reduce a `BLUR_WIDTH` de ancho y se difumina; después la GPU la reamplía
# con filtrado lineal, que es justo lo que hace que el resultado se vea
# suave. Difuminar a tamaño reducido, además, cuesta una fracción de lo que
# costaría hacerlo a resolución completa, y aquí importa porque el fondo se
# regenera en cada movimiento del carrusel.
BLUR_WIDTH = 140
BLUR_RADIUS = 4.0

# Tope de la caché de fondos difuminados. Cada uno ocupa ~80 KB, así que el
# tope es holgado; existe solo para que una biblioteca muy grande no acumule
# una entrada por juego visitado durante toda la sesión.
_BLUR_CACHE_MAX = 32

# Margen extra sobre el frustum calculado, para cubrir de sobra el encuadre
# aunque la cámara no mire exactamente perpendicular al fondo.
_SIZE_MARGIN = 1.4


def _blur_texture(source: Texture) -> Texture:
    """
    Versión reducida y difuminada de `source`, conservando su relación de
    aspecto (el recorte tipo `background-size: cover` depende de ella).

    Devuelve la textura original sin tocar si no se puede leer su imagen en
    RAM: un fondo nítido y pixelado es mejor que ningún fondo.
    """
    image = PNMImage()
    if not source.store(image) or image.get_x_size() == 0:
        return source

    src_w, src_h = image.get_x_size(), image.get_y_size()
    if src_w > BLUR_WIDTH:
        small = PNMImage(BLUR_WIDTH, max(1, round(BLUR_WIDTH * src_h / src_w)))
        small.quick_filter_from(image)  # reducción por promediado de bloques
        image = small

    image.gaussian_filter(BLUR_RADIUS)

    texture = Texture(f"{source.get_name()}-blur")
    texture.load(image)
    # Lineal en ambos sentidos: la ampliación a pantalla completa la hace la
    # GPU y es parte del desenfoque, así que interesa que interpole.
    texture.set_minfilter(Texture.FT_linear)
    texture.set_magfilter(Texture.FT_linear)
    texture.set_wrap_u(Texture.WM_clamp)
    texture.set_wrap_v(Texture.WM_clamp)
    return texture


class Background:
    def __init__(self, base, distance: float = 20.0):
        self._base = base
        self._distance = distance
        self._half_w = 1.0
        self._half_h = 1.0

        card = CardMaker("background")
        card.set_frame(-1, 1, -1, 1)
        self.node: NodePath = base.render.attach_new_node(card.generate())
        # Que no le afecten las luces de la escena: queremos sus colores tal
        # cual, no sombreados como si fuera un objeto 3D más.
        self.node.set_light_off()
        self.node.set_color_scale(1.0 - DARKEN, 1.0 - DARKEN, 1.0 - DARKEN, 1.0)

        self._stage = TextureStage.get_default()
        self._current: Texture | None = None
        self._current_tex_size: tuple[int, int] | None = None
        # id(textura original) -> (textura original, versión difuminada). Se
        # guarda también la original para que su `id()` no pueda reciclarse
        # en otro objeto mientras la entrada siga en caché.
        self._blur_cache: dict[int, tuple[Texture, Texture]] = {}

        self._resize()
        base.accept("window-event", self._on_window_event)

    def _on_window_event(self, window) -> None:
        self._resize()

    def _resize(self) -> None:
        """Recoloca la card al tamaño y distancia actuales de la cámara."""
        world_y = self._base.camera.get_y() + self._distance
        h_fov, v_fov = self._base.camLens.get_fov()
        self._half_w = self._distance * math.tan(math.radians(h_fov) / 2) * _SIZE_MARGIN
        self._half_h = self._distance * math.tan(math.radians(v_fov) / 2) * _SIZE_MARGIN

        self.node.set_pos(0, world_y, 0)
        self.node.set_scale(self._half_w, 1, self._half_h)

        if self._current_tex_size is not None:
            self._apply_cover_fit(*self._current_tex_size)

    def _blurred(self, texture: Texture) -> Texture:
        key = id(texture)
        cached = self._blur_cache.get(key)
        if cached is None:
            if len(self._blur_cache) >= _BLUR_CACHE_MAX:
                self._blur_cache.pop(next(iter(self._blur_cache)))
            cached = (texture, _blur_texture(texture))
            self._blur_cache[key] = cached
        return cached[1]

    def set_cover(self, texture: Texture) -> None:
        if texture is self._current:
            return
        self._current = texture

        blurred = self._blurred(texture)
        self.node.set_texture(blurred)
        self._current_tex_size = (blurred.get_x_size(), blurred.get_y_size())
        self._apply_cover_fit(*self._current_tex_size)

    def _apply_cover_fit(self, tex_w: int, tex_h: int) -> None:
        """
        Ajusta las UV para que la carátula llene la card sin deformarse
        (equivalente a `background-size: cover`), con el acercamiento
        adicional de ZOOM encima. Sin esto, una carátula vertical estirada
        sin más sobre una card ancha se vería aplastada.
        """
        card_aspect = self._half_w / self._half_h
        tex_aspect = tex_w / tex_h

        if tex_aspect > card_aspect:
            crop_u = (card_aspect / tex_aspect) / ZOOM
            crop_v = 1.0 / ZOOM
        else:
            crop_u = 1.0 / ZOOM
            crop_v = (tex_aspect / card_aspect) / ZOOM

        self.node.set_tex_scale(self._stage, crop_u, crop_v)
        self.node.set_tex_offset(self._stage, (1 - crop_u) / 2, (1 - crop_v) / 2)
