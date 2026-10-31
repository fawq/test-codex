# Fotel — model 3D w skali rzeczywistej

Interpretacja fotela z dostarczonego zdjęcia: ciepła, kremowa skorupa, mocno
pochylone oparcie, rdzawa tapicerka, gruby wałek przedni i niska owalna podstawa.
Koc pominięto, aby odsłonić siedzisko. Kształt elementów zasłoniętych na zdjęciu,
tyłu i mocowania podstawy jest założeniem projektowym.

Wersja 2 koryguje przede wszystkim bryłę tapicerki: osobna, zaokrąglona poduszka
zagłówka znajduje się poniżej wyściełanego górnego obrzeża, siedzisko ma gruby,
zaokrąglony wałek przedni i zagłębiony środek, a boki mają wyraźniejsze fałdy
przy szwach. Poszerzono górę oparcia, spłaszczono kremowe nakładki podłokietników
i zastąpiono jasne talerze podstawy ciemnym, cofniętym cokołem.
[Porównanie z poprzednią wersją](review/README.md) pokazuje te zmiany przy tej
samej kamerze i oświetleniu.

## Skala i wymiary

**900 mm szerokości × 1100 mm głębokości × 1150 mm wysokości.**
To zaakceptowane wymiary modelu, a nie pomiar oryginalnego fotela. Jedno zdjęcie
bez znanego wymiaru nie pozwala odtworzyć dokładnej geometrii ani rzeczywistej skali
przedmiotu. Model jest pełnowymiarowy względem tych założeń.

- 1 jednostka Blendera = 1 metr; scena używa jednostek metrycznych.
- X: szerokość, −Y: przód, +Z: góra; podłoga na Z=0.
- Wszystkie siatki mają zastosowaną skalę `(1, 1, 1)`.
- GLB również używa metrów, ale zgodnie z glTF ma oś Y skierowaną w górę.
- Raport `output/model_info.json` zawiera gabaryty obliczone z geometrii.

## Pliki

| Plik | Zawartość |
| --- | --- |
| `output/chair.blend` | Gotowy model, materiały proceduralne, studio i pięć kamer |
| `output/chair.glb` | Sam fotel, bez kamer, świateł i podłogi; przenośny format 3D |
| `output/perspective.png` | Render z przodu pod kątem |
| `output/reference.png` | Dodatkowe ujęcie od strony zbliżonej do referencji |
| `output/front.png`, `side.png`, `top.png` | Rzuty ortograficzne |
| `output/rear.png` | Widok tyłu |
| `output/dimensions.svg` | Samodzielny arkusz rzutów z wymiarami gabarytowymi |
| `build_chair.py` | Samodzielny generator Blendera; bez zewnętrznych bibliotek |
| `validate_model.py` | Weryfikacja plików, wymiarów, jednostek i zamknięcia siatek |

GLB zachowuje podstawowe kolory i materiały PBR. Proceduralny mikrosplot tkaniny
i jego bump pozostają w pliku `.blend`; nie są wypiekane do tekstur GLB.

## Uruchomienie

Sprawdzono w Blenderze **4.3.2**. W katalogu `chair`:

```sh
blender --background --threads 8 --python-exit-code 1 --python build_chair.py -- --output output
blender --background --python-exit-code 1 --python validate_model.py -- output
```

Generator zapisuje `.blend`, `.glb`, raport wymiarów i sześć renderów PNG.
`--no-render` pomija rendery, `--samples 64` skraca renderowanie. Domyślnie 96 próbek.
Nie wymaga pobierania modeli, tekstur ani dodatków. Korzysta z CPU; nie wymaga GPU.

Szybki podgląd w osobnym katalogu, bez zastępowania gotowych wyników:

```sh
blender --background --threads 8 --python-exit-code 1 --python build_chair.py -- --output /tmp/chair-preview --resolution 760 --samples 32 --views perspective reference
```

`--views` wybiera ujęcia. Arkusz `dimensions.svg` powstaje, gdy bieżące uruchomienie
renderuje wszystkie trzy rzuty: `front`, `side` i `top`.

W interfejsie Blendera: otwórz `build_chair.py` w edytorze tekstowym i wybierz
**Run Script**. Pliki trafią do folderu `output` obok skryptu (lub `chair_output`
obok pliku sceny, jeżeli edytor nie udostępnia ścieżki skryptu).
Ponowne uruchomienie zastępuje kolekcję `REFERENCE_CHAIR` i wygenerowane pliki
wyjściowe. Użyj innego katalogu `--output`, aby zachować wcześniejszy wariant.

## Edycja

Najwygodniej otworzyć `output/chair.blend`. Kolekcje rozdzielają skorupę,
tapicerkę, szwy i okucia, podstawę oraz studio. Części są osobnymi siatkami.

Generator zawiera parametry `WIDTH`, `DEPTH`, `HEIGHT`, `SHELL_THICKNESS` oraz
tabelę `PROFILE`, określającą krzywiznę siedziska i oparcia. Funkcja
`padded_patch` modeluje objętość poduszek, przeszycia i marszczenia przy szwach.
Skorupa i poduszki powstają na ciągłej, profilowanej powierzchni i z przekrojów
eliptycznych. Końcowe siatki są wygładzone i zamknięte.

## Dalsza praca nad sklejką i CNC

To model kształtu do oceny proporcji. Skorupa jest pełną, przestrzennie giętą
powłoką o nominalnej grubości 22 mm przed dopasowaniem gabarytów; końcowy zakres
grubości podaje `model_info.json`. Nie oznacza to, że należy wycinać ją jako jedną
płytę sklejki 22 mm. Brak jeszcze zaprojektowanych żeber, łączeń, podpór i tolerancji.

Przed wykrojami CNC trzeba wybrać technologię (np. żebra ze sklejki plus cienkie
poszycie albo laminowanie), zweryfikować ergonomię i przenoszenie obciążeń,
ustalić grubość sklejki, połączenia i narzędzia. Zamknięta siatka ani prawidłowa
skala same w sobie nie potwierdzają wytrzymałości lub wykonalności konstrukcji.
Pliki produkcyjne CNC nie są częścią tej wersji.
