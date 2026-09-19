Pruebas de la versión de un solo archivo ("Tiempo Extra.html").

Necesitan Playwright, que NO es dependencia del programa: sólo de estas
pruebas. El programa sigue sin usar nada que no traiga el navegador.

    pip install playwright
    playwright install chromium

Se corren una por una:

    python pruebas/navegador/lector.py

No se llaman "test_*.py" a propósito, para que "unittest discover" no
intente importarlas cuando no hay Playwright instalado.
