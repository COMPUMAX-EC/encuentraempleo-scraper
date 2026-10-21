# Abre Chrome con un perfil propio y el puerto de depuración 9222 para que scraper.py
# pueda usar la sesión que inicies a mano en Encuentra Empleo.
$perfil = Join-Path $PSScriptRoot "chrome-profile"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
& $chrome --remote-debugging-port=9222 --user-data-dir="$perfil" `
    "https://encuentraempleo.trabajo.gob.ec/socioEmpleo-war/paginas/index.jsf"
