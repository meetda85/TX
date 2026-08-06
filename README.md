# Asignación de Tiempo Extra — TWR MEX

Sistema **local** para publicar tiempo extra, anotar quién lo pidió y decidir a
quién asignárselo, repartiendo parejo entre quienes menos horas llevan.

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

## Cómo se usa: cuatro pasos

El trabajo del día va en línea recta, y cada pantalla lleva a la siguiente.

### 1 · Publicar

Una rejilla de **días × (grupo × turno)** donde anotas cuántos lugares hay.
Puede haber varios el mismo día y para más de un grupo a la vez. Pasa el cursor
por una casilla y salen los botones **−** y **+**; también se teclea el número
directo y las flechas ↑ ↓ mueven de casilla, como en una hoja de cálculo.

Abajo salen **tres mensajes, uno por grupo de WhatsApp**, listos para copiar:

```
Supervisores TWR MEX      ATCO's TWR MEX           AUX's TWR MEX
Buen día, TX disponible:  Buen día, TX disponible: Buen día, TX disponible:
13 en K                   13 en K (3)              14 en K
14 en C y K               14 en C (2)              16 en C (4)
                          15 en C, K y O
```

Los cupos van entre paréntesis sólo cuando hay más de un lugar, y en cuanto un
turno lleva cupo el día se desglosa renglón por renglón — así lo escriben en
los grupos y así se relee sin ambigüedad.

### 2 · Solicitudes

Se capturan a mano, persona por persona: tecleas las siglas y luego lo que
pidió, tal como te lo dijeron.

```
Siglas:  CE
Pidió:   12 en C, 14 en C, 15 C y K
```

Se entiende igual `12c 14c 15 c y k`, y una lista de días con un turno al final
(`11, 12 y 15 en K`). Al agregar, el cursor vuelve a las siglas para seguir con
el siguiente. Cada solicitud queda como una ficha que se puede quitar.

Pegar el mensaje del grupo completo también funciona, pero está en *Más…*: no
se puede depender de que el mensaje llegue en un formato concreto cuando varias
personas usan el sistema.

### 3 · Horas

Sale la lista de **quienes pidieron algo** y capturas las horas que llevan
**trabajadas** al día de hoy, tal como vengan del conteo. Con Enter saltas al
siguiente. Arriba se avisa de quién falta.

Las horas son sólo las trabajadas: el sistema **no** les suma lo que está por
asignarse, porque todavía no se trabaja.

### 4 · Asignar

Lugar por lugar, quién lo pidió **ordenado de menos a más horas trabajadas**.
El primero de cada lista es la sugerencia. Quien no tenga horas capturadas va
al final, porque no hay con qué compararlo.

Si hay horario cargado, se avisa de los choques (que ya trae ese turno, que
juntaría dos turnos el mismo día, que serían tres jornadas dobles seguidas).
El aviso no bloquea: la decisión es del supervisor.

Al final, el mensaje de asignación listo para copiar con su `Pls ack`.

---

## La regla de los tres días

Cuando hay horario base cargado (pestaña *Personal*), el sistema vigila:

> **No puede haber tres días consecutivos de jornada doble.**

Una **jornada doble** es un día en que la persona junta dos turnos troncales.
Se llega ahí por cuatro caminos:

| Camino | Ejemplo |
|---|---|
| El horario base ya trae el turno `f` de 14 horas | `f` = 07:00–21:00 |
| Su turno base más tiempo extra | Trae `C` y se le da TX en `K` → 14 h |
| Dos bloques de TX el mismo día en su descanso | `C` + `K` |
| El conteo registra 14 horas o más ese día | `17` en el Excel = 7 + 10 |

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

## Otras pantallas

Fuera de los cuatro pasos, bajo **Más…** y **Personal**:

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

### Totales

La captura manual de los acumulados que hoy llevas en el Excel. Junto a cada
persona ves la columna **Sistema**, que son las horas que este programa
registró por su cuenta, para cotejar una contra otra.

Desde aquí también se importa el **libro de conteo** (`Controladores`). Lee una
hoja mensual completa y trae dos cosas:

- Los **totales acumulados** de la fila de encabezado.
- El **detalle día por día**, que es lo valioso: un día de 14 horas o más
  cuenta como jornada doble para la regla de días consecutivos, aunque la hoja
  no diga qué turnos fueron. `7` es un turno, `10` es un turno O, `17` es una
  doble.

Las siglas que no estén dadas de alta se registran automáticamente si marcas
la casilla; después les completas el nombre en la pestaña Personal.

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

---

## Sobre el Excel de conteo

El sistema lee `.xlsx` y `.csv` sin librerías externas, y conoce el formato del
libro `Controladores`:

```
        col 0    col 2   col 3   col 4   col 5   …      ← dos columnas por persona
fila 1  Días  |  DT   |       |  RH   |       |         ← siglas
fila 2        |  146  |  0    |  475  |  0    |         ← totales acumulados
fila 3  1-jul |   7   |       |   7   |       |         ← horas de ese día
fila 4  2-jul |       |       |   7   |  10   |         ← 7+10 = 17 h: doble
```

Convive con las dos variantes del libro: las hojas `Julio Twr` y `Agosto Aux`
guardan la fecha completa, mientras que `Enero`…`Diciembre` guardan sólo el
número de día y hace falta indicar el mes. El sistema lo deduce del nombre de
la hoja y avisa si las fechas no cuadran con él.

Para el archivo de Google Sheets que se modifica a diario, la recomendación es:

1. **El día a día** — no sincronizar nada. Al asignar, capturas el acumulado de
   quienes solicitaron directo en la lista de candidatos. Son diez o quince
   números y siempre están al corriente.
2. **De vez en cuando** — `Archivo → Descargar → Microsoft Excel (.xlsx)` y lo
   importas completo desde *Totales*, para traer el detalle diario que alimenta
   la regla.
3. **Conexión automática** — pendiente. Requiere publicar la hoja o dar de alta
   una credencial de Google.

---

## Estructura del proyecto

```
tx/
  turnos.py     Catálogo de turnos, horarios y encadenamientos
  reglas.py     Motor de reglas: jornada doble y días consecutivos
  db.py         SQLite: personal, horario, vacantes, asignaciones, totales
                y horas del conteo histórico
  api.py        Endpoints JSON
  servidor.py   Servidor HTTP local
  whatsapp.py   Lectura y redacción de los mensajes del grupo
  xlsx.py       Lector de .xlsx sin dependencias
  importar.py   Importadores de horario mensual y del libro de conteo
  semilla.py    Horario de agosto 2026 de S-TWR para arrancar
  web/          Interfaz (HTML, CSS y JavaScript sin frameworks)
datos/          Base de datos local (no se versiona)
pruebas/        161 pruebas automatizadas
```

## Pruebas

```
python3 -m unittest discover -s pruebas
```

Cubren el motor de reglas (incluido el caso textual de la jefatura), el parser
de WhatsApp contra mensajes reales de los tres grupos, la lectura del libro de
conteo en sus dos formatos, y la API completa.

## Respaldos

Todo vive en `datos/tx.db`. Para respaldar, copia ese archivo. Para restaurar,
devuélvelo a su lugar con el programa cerrado.
