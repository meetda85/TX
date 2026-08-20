# Asignación de Tiempo Extra — TWR MEX

Sistema **local** para publicar tiempo extra, anotar quién lo pidió y decidir a
quién asignárselo, repartiendo parejo entre quienes menos horas llevan.

Corre en tu propia computadora. No manda nada a internet y no necesita cuenta
ni servidor.

---

## Cómo abrirlo

Hay dos versiones. Hacen lo mismo; cambia dónde guardan.

### Un solo archivo — sin instalar nada

Doble clic en **[`Tiempo Extra.html`](Tiempo%20Extra.html)** y listo. Se abre en
Chrome o Edge y ya está funcionando: no hace falta Python, ni permisos de
administrador, ni internet.

**Para instalarla de verdad** —menú de inicio, ventana propia, «Aplicaciones
instaladas» de Windows— doble clic en **`Abrir como app.bat`** y luego en el
botón **Instalar** que sale arriba. Una sola vez; después la ventana negra ya no
hace falta.

> El navegador **no deja instalar un archivo abierto con doble clic**: el
> registro falla con *«the URL protocol of the current origin ('null') is not
> supported»*. Tiene que venir servido. El lanzador lo sirve desde la propia
> computadora, en `127.0.0.1`, usando el PowerShell que Windows ya trae — no
> instala nada y no sale nada a la red. Ya instalada abre sin el lanzador y sin
> internet, porque el service worker guarda el programa entero.

Si el equipo bloquea PowerShell, o no quieres instalarla, el doble clic en el
HTML sigue funcionando igual. Para tener el ícono a la mano, pon `TX.ico` y
`Crear acceso directo.bat` junto al HTML y corre el `.bat` una vez; a mano
funciona igual con clic derecho → *Enviar a* → *Escritorio*.

Lo capturado se guarda solo en la memoria del navegador de esa computadora, así
que **saca una copia con el botón «Respaldo»** al terminar cada asignación: baja
un archivo `.json` con todo, que sirve para resguardar o para pasarlo a otra
máquina. Esa memoria se borra si alguien limpia los datos de navegación, y el
archivo es lo único que la sobrevive.

### El programa completo — con Python

Guarda en una base de datos en tu disco, saca respaldos solo y puede importar el
Excel de conteo. Vale la pena si vas a manejar mucho histórico.

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

El paso a paso de las dos versiones —incluido qué hacer cuando algo falla— está
en **[`COMO_INSTALAR.txt`](COMO_INSTALAR.txt)**, en texto plano para abrirlo con
doble clic en el Bloc de notas.

---

## Cómo se usa: cinco pasos

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

**Lugares compartidos entre grupos.** A veces los mismos lugares se publican en
dos grupos a la vez: hay 2 el 18 en C y se anuncian en torre y en auxiliares,
porque los cubre cualquiera de los dos. Capturarlos como 2 y 2 daría 4, que no
es lo que hay. El botón **⇄** debajo de la casilla los abre a los grupos que
elijas **sin duplicarlos**: siguen siendo 2, salen en los dos mensajes, y en
cuanto alguien toma uno se descuenta del mismo bote y deja de republicarse en
ambos lados. La casilla queda marcada con `+A` o `+T` según con quién se
comparte.

### 2 · Solicitudes

Se capturan a mano, persona por persona: tecleas las siglas y luego lo que
pidió, tal como te lo dijeron.

```
Siglas:  CE
Pidió:   12 en C, 14 en C, 15 C y K
```

Se entiende igual `12c 14c 15 c y k` o `15COK` pegado. Al agregar, el cursor
vuelve a las siglas para seguir con el siguiente, y cada solicitud queda como
una ficha que se puede quitar.

**Varios días en el mismo turno**, con o sin separadores:

```
11, 12 y 15 en K     23 24 25 26 en C     23 al 26 en C     23-26 en C
```

**«Uno u otro».** Hay quien pide *uno de los dos*, no los dos. Se escribe con
**diagonal** y funciona igual entre turnos del mismo día que **entre días
distintos**:

```
25 en C/K        →  el 25, o en C o en K
28C / 30C        →  o el 28 en C, o el 30 en C
```

Quedan pintados juntos en una sola ficha con la diagonal en medio. En cuanto se
le asigna uno, **los demás del grupo dejan de ofrecerse** y el botón dice cuál
ya tiene. La **✂** los separa si se entendió mal.

> La palabra `o` también funciona, pero la diagonal es más segura: `o` se
> parece al turno `O`. El sistema los distingue por la forma —una `o` suelta
> entre dos letras es conjunción, el turno `O` va pegado (`COK`) o en lista
> (`C, O y K`)— pero con `/` no hay nada que adivinar.

En la versión de Python se puede además pegar el mensaje del grupo completo,
desde *Más…*. En la de un solo archivo no: la captura es a mano, a propósito,
porque no se puede depender de que el mensaje llegue en un formato concreto
cuando varias personas usan el sistema.

### 3 · Horas

Sale la lista de **quienes pidieron algo** y capturas las horas que llevan
**trabajadas** al día de hoy, tal como vengan del conteo. Con Enter saltas al
siguiente. Arriba se avisa de quién falta.

Las horas son sólo las trabajadas: el sistema **no** les suma lo que está por
asignarse, porque todavía no se trabaja.

### 4 · Asignar

**Un día por tarjeta**, y adentro un bloque por categoría. Cada bloque abre con
los lugares que hay ese día y cómo van (`C 1/2`, `K 0/1`), y sigue con **todos
los que pidieron ese día**, ordenados de menos a más horas trabajadas. El
primero de cada lista es la sugerencia; quien no tenga horas capturadas va al
final, porque no hay con qué compararlo.

Cuando un turno está compartido con otro grupo, su contador lo dice (`C 0/2 +A`)
y en la lista aparecen los candidatos de las dos categorías, con una etiqueta
que marca a los de fuera.

Cada persona ocupa **un solo renglón por día**, con los turnos que pidió como
botones. Pulsas el turno y queda asignado; **vuelves a pulsarlo y se quita**,
con el lugar de regreso a la lista de libres. Cuando un turno se llena, a los
demás se les desactiva ese botón.

**Los avisos.** El renglón se marca —y destella al asignar— cuando algo no
cuadra, de más a menos grave:

| Aviso | Qué es |
|---|---|
| Ya tiene ese turno ese día | Duplicado |
| Serían 3 jornadas dobles seguidas | La regla dura: tres días encadenando dos turnos |
| Serían 3 días seguidos con TX | Tiempo extra tres días al hilo, del tamaño que sea |

El tercero no está prohibido, pero es justo lo que se pasa de noche si nadie lo
suma. Sale **antes** de pulsar, no después.

Ninguno bloquea: la decisión es del supervisor. Y todos ven sólo lo que este
sistema tiene asignado — si alguien recibió tiempo extra por fuera, o viene de
un turno del rol, eso no aparece.

Abajo, antes del mensaje, **«Lo que quedó asignado»**: un renglón por
asignación —siglas, nombre, día, turno, categoría— ordenado por siglas, que es
como está armado el rol.

**Sólo lo de la ronda en curso.** Lo asignado en rondas anteriores ya se anunció
y ya se anotó; volver a sacarlo aquí haría repetirle el mensaje a quien ya le
avisaron. En las tarjetas de arriba sí sigue a la vista —con su etiqueta
`ronda 1` y el turno en gris— porque ocupa el lugar y hay que poder quitárselo;
lo demás está en el Resumen, bajo «Rondas anteriores».

La tabla sirve para dos cosas que el mensaje de WhatsApp no hace bien:

- **Pasarlo al Excel.** El mensaje está escrito para leerse en el grupo
  (`CT y ZL 17C`) y hay que ir desarmándolo. El botón **Copiar para Excel**
  copia la tabla con tabuladores: al pegarla cae una celda por columna.
- **Corregir.** Cada renglón trae su **×** para deshacer esa asignación sin
  tener que ir a buscarla entre las tarjetas de arriba.

Cada renglón lleva además su **nota**: por qué se le dio a esa persona. Se
escribe en un clic y se copia junto con lo demás, así que cuando pregunten hay
respuesta en vez de tener que acordarse.

Debajo, **«Notas de esta asignación»** es la libreta de la semana entera —los
acuerdos, quién no podía, qué se cambió a última hora—. Se guarda sola mientras
escribes y va en el respaldo.

Y al final sí, el mensaje de asignación listo para copiar con su `Pls ack`.

### 5 · Resumen

El corte claro de cómo va la publicación, que es otra pregunta distinta a «a
quién le asigno»:

- Tres marcadores grandes: **publicados**, **ya cubiertos** y **siguen libres**,
  con el porcentaje de avance y el desglose por grupo.
- **Todavía sin cubrir**, día por día: qué turno, de qué grupo, quién va ya y
  cuántos faltan. En la ronda 2 o 3 dice además a qué grupos se les está
  ofreciendo.
- **Ya cubierto**, con los nombres de quienes quedaron.

**El cierre de la ronda vive aquí.** Si no quedó nada libre, se ofrece cerrar la
asignación y ahí se acaba. Si quedaron lugares, se ofrece **pasar a la ronda
siguiente**: lo ya asignado se queda como está, la ronda que termina se pliega
en **Rondas anteriores**, y **los mensajes para volver a publicar salen en esa
misma pantalla** — no hay que regresar al paso 1. De ahí se sigue al paso 2 a
anotar quién contestó.

Al pasar de ronda, **las solicitudes se vacían**: en la ronda nueva vuelven a
pedir todos, y arrastrar las de la anterior sólo daría candidatos que ya no
aplican. Lo asignado se queda —ya está dado— y las horas también, porque no
cambian de una ronda a otra. Quien alcanzó lugar en la ronda anterior sigue
apareciendo en su tarjeta con el turno marcado, para poder quitárselo si hace
falta.

Es un camino de ida: cada ronda deja su renglón en el historial —cuántos se
asignaron, cuántos quedaron, con qué siglas— para saber después en cuál se
cubrió cada cosa. Si se pasó de ronda sin querer, **Reabrir** lo deshace.

---

## Empezar una asignación nueva

El botón **⟳ Nueva asignación** de la barra superior vacía lo del ciclo
anterior. Es lo primero que se hace cada semana.

Como ahí arriba es fácil no verlo —y capturar la semana nueva encima de la
anterior—, **al abrir el paso 1 sale un aviso** cuando quedaron datos del ciclo
pasado, con la cuenta de lo que hay y los dos caminos: limpiar, o seguir con
ésos. El aviso se calla el resto de la sesión en cuanto eliges seguir.

Lo que se borra por omisión:

| Se borra | Se conserva |
|---|---|
| Lugares publicados | Catálogo de personal |
| Solicitudes capturadas | Horario base del mes |
| Asignaciones hechas | Histórico importado del Excel |
| Horas capturadas | |

El personal, el horario y el histórico son el **cimiento**, no el ciclo:
recapturarlos cada semana no tendría sentido. Las horas sí se limpian, porque
las vuelves a tomar del conteo cada vez y **una cifra vieja ordenaría mal la
sugerencia sin que te dieras cuenta**.

Las casillas se pueden cambiar una por una. Borrar el catálogo de personal pide
además la clave, porque arrastra consigo asignaciones y solicitudes.

Salvaguardas, porque esto no se deshace y se hace todas las semanas:

- Hay que **escribir `LIMPIAR`** para que el botón se active. Un clic de más no
  basta.
- Antes de borrar se guarda un **respaldo** en `datos/respaldos/`, con fecha y
  hora en el nombre. Para restaurarlo, cierra el programa y copia ese archivo
  encima de `datos/tx.db`.
- Al terminar vuelve a la **ronda 1**.

---

## El catálogo de personal

Está en la pestaña **Personal** y sirve para dar de alta, cambiar de categoría
a quien asciende (de torre a supervisor, por ejemplo) y dar de baja a quien
deja la torre.

**Modificarlo pide una clave.** La inicial es `0348` y se puede cambiar desde
la misma pantalla. Consultar la lista es libre; sólo los cambios están bajo
llave.

> La clave es un seguro contra cambios accidentales, **no una medida de
> seguridad**. Cuatro dígitos son diez mil combinaciones, y quien tenga el
> archivo `datos/tx.db` en las manos puede editarlo por fuera del programa.
> Sirve para que la lista no se modifique de pasada cuando varias personas
> usan la misma computadora, que es el problema real.

La clave no se guarda en claro: se almacena su derivación PBKDF2 con sal, para
que no quede a la vista de quien abra la base por curiosidad. Si se pierde, se
recupera borrando el ajuste `clave_personal` de la tabla `ajustes`.

---

## Las tres rondas

El tiempo extra se publica en tres rondas separadas en el tiempo. Cada una
reofrece **sólo lo que quedó sin cubrir** de la anterior, y lo sobrante va
subiendo de categoría.

**El tiempo extra sólo sube, nunca baja.** Un auxiliar no puede cubrir un
puesto de torre, así que un lugar de torre jamás se ofrece al grupo de
auxiliares. Al revés sí: torre alcanza para auxiliar, y supervisor para todo.

| Quién | Puede cubrir |
|---|---|
| Auxiliar | auxiliar |
| Torre (ATCO) | torre y auxiliar |
| Supervisor | las tres |

De ahí sale a qué grupos llega cada lugar en cada ronda:

| Lugar de… | Ronda 1 | Ronda 2 | Ronda 3 |
|---|---|---|---|
| **Auxiliares** | auxiliares | auxiliares + torre | auxiliares + torre + supervisores |
| **Torre** | torre | torre | torre + supervisores |
| **Supervisor** | supervisores | supervisores | supervisores |

La ronda se elige en el selector de la barra superior y queda guardada. Los
mensajes y la lista de candidatos se recalculan solos.

Cuando a un grupo le llega un lugar que no es de su categoría, va en un bloque
aparte encabezado *«TX disponible aún de otra categoría:»* — la misma frase que
se usa hoy en los chats.

```
ATCO's TWR MEX  ·  ronda 2

Buen día, sigue disponible TX:
12 en C (2)
13 en K (3)

TX disponible aún de otra categoría:
14 en K
16 en C (4)
```

Al asignar, el sistema **rechaza** que alguien tome un puesto por encima de su
categoría, en cualquier ronda. Y en la lista de candidatos, quien viene de otra
categoría lleva una etiqueta para que se note de dónde salió.

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

Fuera de los cinco pasos, bajo **Más…**:

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
  acceso.py     Candado del catálogo de personal (PBKDF2 con sal)
  semilla.py    Horario de agosto 2026 de S-TWR para arrancar
  web/          Interfaz (HTML, CSS y JavaScript sin frameworks)
Tiempo Extra.html   La versión de un solo archivo: misma interfaz y mismas
                    reglas, en JavaScript, guardando en el navegador
datos/          Base de datos local (no se versiona)
pruebas/        231 pruebas automatizadas
```

## Pruebas

```
python3 -m unittest discover -s pruebas
```

Cubren el motor de reglas (incluido el caso textual de la jefatura), el parser
de WhatsApp contra mensajes reales de los tres grupos, la lectura del libro de
conteo en sus dos formatos, y la API completa.

## Respaldos

**Con Python** todo vive en `datos/tx.db`. Para respaldar, copia ese archivo;
para restaurar, devuélvelo a su lugar con el programa cerrado. El botón de
limpieza saca su propia copia en `datos/respaldos/` antes de borrar nada.

**En la versión de un solo archivo** los datos están en la memoria del navegador,
que no es un lugar del que se pueda copiar a mano. Ahí el respaldo es el botón
**Respaldo → Guardar copia en un archivo**: baja un `.json` con el catálogo de
personal, los lugares, las solicitudes, las horas y las asignaciones. Recuperarlo
reemplaza todo lo que haya en ese momento. Al limpiar para empezar la semana
saca esa copia sola, salvo que lo desmarques.
