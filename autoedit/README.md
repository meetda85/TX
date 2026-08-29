# autoedit — edición automática de vídeo

Script en Python que aplica un estilo de edición dinámico, pensado para redes
sociales, a todos los vídeos de una carpeta. Procesa de uno en uno y guarda los
resultados en una subcarpeta nueva.

## Qué hace a cada vídeo

| Regla | Implementación |
|---|---|
| **Cortes rápidos** | `silencedetect` localiza los silencios; se recortan dejando 60 ms de aire a cada lado (jump cut limpio, sin cortar la respiración). |
| **Zoom dinámico** | `zoompan` con rampa lineal por plano, alternando acercar/alejar y variando la intensidad entre 5 % y 10 % para que no se sienta mecánico. Los planos de más de 4 s se trocean para que el zoom cambie de forma periódica. |
| **Glitch en el corte** | `rgbashift` (separación RGB) + `noise`, activos solo los primeros 70 ms de cada plano. No se aplica al primer plano, donde no hay corte entrante. |
| **Color y contraste** | `eq` (contraste 1.06, saturación 1.12, gamma 1.02) + `vibrance` + un `unsharp` suave. |

Se añade un fundido de audio de 12 ms en cada extremo de cada plano: sin él, los
cortes producen chasquidos audibles.

## Requisitos

- **Python 3.8+** (solo librería estándar, no hay que instalar nada con `pip`)
- **FFmpeg** con `ffmpeg` y `ffprobe` en el PATH

```bash
# macOS
brew install ffmpeg
# Windows
winget install Gyan.FFmpeg
# Linux
sudo apt install ffmpeg
```

## Uso

```bash
# Busca los vídeos en tu carpeta de Documentos y los edita
python3 autoedit.py

# Ver primero qué haría, sin generar archivos (recomendado la primera vez)
python3 autoedit.py --dry-run

# Otra carpeta, incluyendo subcarpetas
python3 autoedit.py --input-dir "/ruta/a/videos" --recursive

# Versión vertical 9:16 para Reels / TikTok / Shorts
python3 autoedit.py --vertical
```

Salida por defecto: `<carpeta de entrada>/Videos_Editados/<nombre>_editado.mp4`.
Los vídeos ya editados se omiten salvo que uses `--overwrite`.

## Ajustes habituales

Si **corta demasiado** (se come palabras), baja el umbral y exige silencios más largos:

```bash
python3 autoedit.py --noise-db -40 --min-silence 0.7 --padding 0.12
```

Si **no corta nada**, sube el umbral: `--noise-db -26`.

| Opción | Por defecto | Para qué |
|---|---|---|
| `--noise-db` | `-32` | Umbral de silencio en dB. Más bajo = corta menos. |
| `--min-silence` | `0.45` | Silencio mínimo (s) para considerarlo pausa muerta. |
| `--padding` | `0.06` | Aire conservado a cada lado del corte (s). |
| `--max-shot` | `4.0` | Trocea planos más largos para variar el zoom. `0` lo desactiva. |
| `--zoom-min` / `--zoom-max` | `0.05` / `0.10` | Rango de zoom (5 %–10 %). |
| `--zoom-quality` | `fast` | `smooth` sobremuestrea: menos temblor, ~2× más lento. |
| `--glitch-shift` | `5` | Píxeles de separación RGB. `--no-glitch` lo quita. |
| `--saturation` | `1.12` | Saturación. `--no-color` deja el color intacto. |
| `--crf` / `--preset` | `20` / `medium` | Calidad y velocidad de H.264. |
| `--vertical` | off | Exporta 1080×1920 con fondo desenfocado. |

`python3 autoedit.py --help` lista todas.

## Comportamiento en casos límite

- **Vídeo sin audio**, o con pista muda: no se puede detectar silencio, así que se
  conserva entero y se aplica solo el estilo visual (zoom, color, glitch).
- **Vídeo entero por debajo del umbral**: se avisa y se conserva entero, en lugar
  de producir un archivo vacío.
- **Planos más cortos que `--min-clip`** (0,3 s) se descartan: evita el parpadeo.
- `Ctrl-C` interrumpe de forma limpia y borra los temporales.

## Verificación

Probado sobre un clip sintético de 20 s con silencios conocidos en 3–5 s, 9–11,5 s
y 16–18 s:

- los 3 silencios se detectan y el resultado dura 13,9 s (6,1 s eliminados, el
  total esperado menos el *padding*);
- al reanalizar la salida quedan **0** silencios;
- el zoom se confirmó sobre una fuente estática (diferencia media de 8,6/255 entre
  el primer y el último fotograma de un plano);
- salidas válidas y decodificables en horizontal y en vertical (1080×1920).
