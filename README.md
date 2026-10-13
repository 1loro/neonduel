# NEON DUEL

Duelo 1 vs 1 de motos de luz para dos jugadores en el mismo teclado. Rápido, frenético y con pixel art de neón.

## Jugar

Descarga [`dist/NeonDuel.exe`](dist/NeonDuel.exe) y ábrelo. Funciona en Windows sin instalar nada.

## Controles

| | Cian | Magenta |
|---|---|---|
| Moverse | W A S D | Flechas |
| Turbo | Mantener la dirección en la que vas | Mantener la dirección en la que vas |

`P` / `ESC` pausa · `F11` pantalla completa · en el menú, `C` para jugar contra la CPU.

## Reglas

- No choques con muros ni estelas. Gana la partida quien llegue antes a 3 puntos.
- Cada ronda acelera con el tiempo, y a los 20 s el muro empieza a cerrarse anillo a anillo.
- El turbo te hace avanzar el doble de rápido y gasta la barra de energía.
- Objetos:
  - **Rayo:** recarga el turbo al máximo.
  - **Fantasma:** atraviesas estelas durante un momento.
  - **Bomba:** borra las estelas a tu alrededor.

## Desde el código

```
pip install -r requirements.txt
python neon_duel.py
```

Para generar el ejecutable:

```
pip install pyinstaller
pyinstaller --onefile --windowed --name NeonDuel neon_duel.py
```
