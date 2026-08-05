# Asignación de Tiempo Extra — TWR MEX

Sistema **local** para que el supervisor publique, controle y asigne tiempo
extra, con la regla de días consecutivos aplicada automáticamente.

Corre en tu propia computadora. No manda nada a internet, no necesita cuenta
ni servidor: los datos viven en un archivo dentro de la carpeta `datos/`.

---

## Cómo abrirlo

**Windows** — doble clic en `iniciar.bat`.
**Mac o Linux** — doble clic en `iniciar.sh`, o desde la terminal:

```
python3 -m tx
```

Se abre solo en el navegador, en `http://127.0.0.1:8787/`. Para cerrarlo,
`Ctrl+C` en la ventana negra o simplemente ciérrala.

Lo único que hace falta instalar una vez es **Python 3.9 o más nuevo**
([python.org/downloads](https://www.python.org/downloads/) — en Windows marca
la casilla *«Add Python to PATH»*). No se instala ninguna otra librería: el
programa usa exclusivamente lo que Python trae de fábrica, para que funcione
en máquinas con permisos restringidos y sin internet.

---

## La regla que aplica

> **No puede haber tres días consecutivos de jornada doble.**

Una **jornada doble** es un día en que la persona junta dos turnos troncales.
Se llega ahí por tres caminos:

| Camino | Ejemplo |
|---|---|
| El horario base ya trae el turno `f` de 14 horas | `f` = 07:00–21:00 |
| Su turno base más tiempo extra | Trae `C` y se le da TX en `K` → 14 h |
| Dos bloques de TX el mismo día en su descanso | `C` + `K` |

Además, el turno `O` (21:00–07:00) **encadena** con el `C` del día siguiente:
quien sale a las 07:00 y vuelve a entrar a las 07:00 lleva 17 horas corridas.
Ese encadenamiento cuenta como jornada doble del día en que se juntan.

Cada turno pertenece al día en que **arranca**: el `O` del día 10 es del día 10.

Con dos jornadas dobles seguidas el sistema **avisa**; a la tercera **bloquea**
la asignación y explica por qué. El supervisor siempre puede forzarla bajo su
criterio, y entonces queda marcada en rojo en la cuadrícula.

El tope es configurable desde el botón ⚙ por si cambia la normativa.

### Catálogo de turnos

Tomado de la tabla «EQUIVALENCIA DE TURNOS» del *Horario de Trabajo S-TWR*:

```
A 06:00-13:00      a 07:00-13:00      #   Descanso semanal
C 07:00-14:00      b 08:00-14:00      *#  Descanso adicional
K 14:00-21:00      x 14:00-20:00      *   Vacaciones
M 16:00-23:00      f 07:00-21:00      +   Periodo de recuperación
O 21:00-07:00                         *** Equipo de reserva
Z 09:00-18:00                         **  Estímulos y recompensas
E 08:00-15:00                         xx  En cuarentena
G 09:00-16:00                         sim Simulador
```

Los turnos que se publican como tiempo extra son **C**, **K** y **O**.

---

## Las pantallas

### Cuadrícula

La vista principal: **personal en filas, días del mes en columnas**. Cada celda
lleva el turno base con su color, y quien trae tiempo extra lleva subrayado
rosa y el turno añadido (`C +K`).

- Las **jornadas dobles** llevan marco ámbar y rayado diagonal.
- Al llegar al límite aparece un contador con la racha (`2`, `3`…).
- Lo que **rompe la regla** se pinta en rojo y parpadea.
- Un punto rosa señala las asignaciones **sin acuse**.

Clic en cualquier celda para anotar tiempo extra, corregir el turno base o
quitar una asignación. El evaluador corre en vivo mientras eliges el turno.

Hay cuatro tamaños de celda —hasta *Enorme*— para cuando la cuadrícula se
consulta de lejos o en pantalla compartida. El filtro «Sólo quien trae TX»
deja únicamente a los involucrados.

### Asignar

Eliges día, turno y ubicación, y te muestra a **todo el personal ordenado**:
primero quien sí puede, y dentro de cada grupo **quien menos tiempo extra
lleva en el mes**, para que el reparto salga parejo. A cada quien le pone su
semáforo con el motivo en texto claro.

### Vacantes

Pegas el mensaje de «TX disponible» tal como lo mandas al grupo y el sistema lo
convierte en vacantes. Entiende los formatos que se usan hoy:

```
Buen día TX disponible :        Tx disponible:              9 O
Spvr                            Jueves 6 en C y K           10 C y K
13 K, 14 C y K, 15 C y K        sábado 1 en C (4)           11 C
```

### Totales

La captura manual de los acumulados que hoy llevas en el Excel. Junto a cada
persona ves la columna **Sistema**, que son las horas que este programa
registró por su cuenta, para cotejar una contra otra. También importa un
`.xlsx` o `.csv`.

### Mensajes

- **Leer solicitudes**: pegas lo que pide la gente (`☝🏼 11, 12, 13 y 15 en K`)
  y lo liga a la persona.
- **Redactar la asignación**: genera el mensaje listo para copiar y pegar en
  WhatsApp, con el mismo formato de siempre y su `Pls ack`.
- **Cargar histórico**: subes el `.txt` que exporta WhatsApp del grupo y el
  sistema recorre todo el chat reconstruyendo qué tiempo extra se asignó y a
  quién. Así la cuadrícula arranca con el historial ya cargado, sin capturar
  nada a mano.

### Personal

Alta y edición de personas, e importación del horario mensual desde el Excel
que ya generan (`HORARIO DE TRABAJO S-TWR`). Detecta sola la fila de días y la
columna de siglas, y te enseña una previa antes de escribir nada.

---

## Sobre el Excel de conteo

El sistema lee `.xlsx` y `.csv` sin librerías externas.

Para el archivo de Google Sheets que se modifica a diario hay dos caminos:

1. **Descargar y arrastrar** — `Archivo → Descargar → Microsoft Excel (.xlsx)`
   y súbelo en *Totales → Importar de Excel*. Funciona hoy, sin configurar nada.
2. **Conexión automática** — pendiente. Requiere publicar la hoja o dar de alta
   una credencial de Google; queda como siguiente paso una vez que veamos la
   estructura real del archivo.

---

## Estructura del proyecto

```
tx/
  turnos.py     Catálogo de turnos, horarios y encadenamientos
  reglas.py     Motor de reglas: jornada doble y días consecutivos
  db.py         SQLite: personal, horario, vacantes, asignaciones, totales
  api.py        Endpoints JSON
  servidor.py   Servidor HTTP local
  whatsapp.py   Lectura y redacción de los mensajes del grupo
  xlsx.py       Lector de .xlsx sin dependencias
  importar.py   Importadores de horario y totales
  semilla.py    Horario de agosto 2026 de S-TWR para arrancar
  web/          Interfaz (HTML, CSS y JavaScript sin frameworks)
datos/          Base de datos local (no se versiona)
pruebas/        83 pruebas automatizadas
```

## Pruebas

```
python3 -m unittest discover -s pruebas
```

Cubren el motor de reglas (incluido el caso textual de la jefatura), el parser
de WhatsApp contra mensajes reales de los tres grupos, y la API completa.

## Respaldos

Todo vive en `datos/tx.db`. Para respaldar, copia ese archivo. Para restaurar,
devuélvelo a su lugar con el programa cerrado.
