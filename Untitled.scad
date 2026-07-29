/*
    Gabinete dividido en dos mitades

    - Panel frontal y trasero independientes
    - Tapa superior con mitad superior de los laterales
    - Tapa inferior con mitad inferior de los laterales
    - Dos postes longitudinales en cada tapa
    - Tornillos desde el frente y desde atrás

    Unidades: milímetros
*/

$fn = 64;


// ============================================================
// PARÁMETROS PRINCIPALES
// ============================================================

// Dimensiones exteriores del gabinete
ancho = 160;
alto = 80;
profundidad = 120;

// Espesor de paredes
pared = 2.4;

// Altura de cada mitad
altura_mitad = alto / 2;


// ============================================================
// PANELES FRONTAL Y TRASERO
// ============================================================

// Espesor de los paneles generados
espesor_panel = 3;

// Los postes comienzan detrás del panel frontal
// y terminan antes del panel trasero.
retroceso_frontal = espesor_panel;
retroceso_trasero = espesor_panel;


// ============================================================
// POSTES PARA TORNILLOS
// ============================================================

// Diámetro exterior de cada poste
diametro_poste = 10;

// Agujero para tornillo autorroscante de aproximadamente 3 mm
diametro_agujero = 2.7;

// Profundidad del agujero en cada extremo
profundidad_agujero = 15;

// Distancia entre el centro del poste y el lateral
margen_poste_x = 10;

// Distancia entre el centro del poste y piso/techo
margen_poste_z = 10;

// Espesor mínimo de los nervios
espesor_nervio = 2.4;


// ============================================================
// ENCASTRE ENTRE LAS DOS TAPAS
// ============================================================

// Activar o desactivar el labio de alineación
usar_encastre = true;

// Dimensiones del labio
altura_labio = 3;
espesor_labio = 1.2;

// Holgura de impresión
holgura_encastre = 0.25;


// ============================================================
// VISUALIZACIÓN
// ============================================================

// Opciones:
// "inferior"
// "superior"
// "conjunto"
// "separadas"

pieza = "separadas";


// ============================================================
// POSTE LONGITUDINAL
// ============================================================

module poste_longitudinal(
    x,
    z,
    lado = "izquierdo",
    fijacion_vertical = "inferior"
) {
    radio = diametro_poste / 2;

    longitud_poste =
        profundidad
        - retroceso_frontal
        - retroceso_trasero;

    difference() {
        union() {

            // ------------------------------------------------
            // Cilindro principal
            // ------------------------------------------------

            translate([
                x,
                retroceso_frontal,
                z
            ])
                rotate([-90, 0, 0])
                    cylinder(
                        h = longitud_poste,
                        d = diametro_poste
                    );


            // ------------------------------------------------
            // Nervio hacia el lateral izquierdo
            // ------------------------------------------------

            if (lado == "izquierdo") {
                translate([
                    pared - 0.1,
                    retroceso_frontal,
                    z - radio
                ])
                    cube([
                        x - pared + radio + 0.2,
                        longitud_poste,
                        diametro_poste
                    ]);
            }


            // ------------------------------------------------
            // Nervio hacia el lateral derecho
            // ------------------------------------------------

            if (lado == "derecho") {
                translate([
                    x - radio,
                    retroceso_frontal,
                    z - radio
                ])
                    cube([
                        ancho - pared - x + radio + 0.1,
                        longitud_poste,
                        diametro_poste
                    ]);
            }


            // ------------------------------------------------
            // Nervio hacia el piso
            // ------------------------------------------------

            if (fijacion_vertical == "inferior") {
                translate([
                    x - radio,
                    retroceso_frontal,
                    pared - 0.1
                ])
                    cube([
                        diametro_poste,
                        longitud_poste,
                        z - pared + radio + 0.2
                    ]);
            }


            // ------------------------------------------------
            // Nervio hacia el techo
            // ------------------------------------------------

            if (fijacion_vertical == "superior") {
                translate([
                    x - radio,
                    retroceso_frontal,
                    z - radio
                ])
                    cube([
                        diametro_poste,
                        longitud_poste,
                        altura_mitad
                            - pared
                            - z
                            + radio
                            + 0.2
                    ]);
            }
        }


        // ----------------------------------------------------
        // Agujero desde el frente
        // ----------------------------------------------------

        translate([
            x,
            retroceso_frontal - 0.1,
            z
        ])
            rotate([-90, 0, 0])
                cylinder(
                    h = profundidad_agujero + 0.1,
                    d = diametro_agujero
                );


        // ----------------------------------------------------
        // Agujero desde atrás
        // ----------------------------------------------------

        translate([
            x,
            profundidad
                - retroceso_trasero
                - profundidad_agujero,
            z
        ])
            rotate([-90, 0, 0])
                cylinder(
                    h = profundidad_agujero + 0.1,
                    d = diametro_agujero
                );
    }
}


// ============================================================
// TAPA INFERIOR
// ============================================================

module tapa_inferior() {
    difference() {
        union() {

            // ------------------------------------------------
            // Piso
            // ------------------------------------------------

            cube([
                ancho,
                profundidad,
                pared
            ]);


            // ------------------------------------------------
            // Mitad inferior del lateral izquierdo
            // ------------------------------------------------

            cube([
                pared,
                profundidad,
                altura_mitad
            ]);


            // ------------------------------------------------
            // Mitad inferior del lateral derecho
            // ------------------------------------------------

            translate([
                ancho - pared,
                0,
                0
            ])
                cube([
                    pared,
                    profundidad,
                    altura_mitad
                ]);


            // ------------------------------------------------
            // Poste inferior izquierdo
            // ------------------------------------------------

            poste_longitudinal(
                x = margen_poste_x,
                z = margen_poste_z,
                lado = "izquierdo",
                fijacion_vertical = "inferior"
            );


            // ------------------------------------------------
            // Poste inferior derecho
            // ------------------------------------------------

            poste_longitudinal(
                x = ancho - margen_poste_x,
                z = margen_poste_z,
                lado = "derecho",
                fijacion_vertical = "inferior"
            );
        }


        // ----------------------------------------------------
        // Canales para recibir los labios de la tapa superior
        // ----------------------------------------------------

        if (usar_encastre) {

            // Canal izquierdo
            translate([
                pared - holgura_encastre,
                -0.1,
                altura_mitad - altura_labio
            ])
                cube([
                    espesor_labio
                        + 2 * holgura_encastre,
                    profundidad + 0.2,
                    altura_labio + 0.1
                ]);


            // Canal derecho
            translate([
                ancho
                    - pared
                    - espesor_labio
                    - holgura_encastre,
                -0.1,
                altura_mitad - altura_labio
            ])
                cube([
                    espesor_labio
                        + 2 * holgura_encastre,
                    profundidad + 0.2,
                    altura_labio + 0.1
                ]);
        }
    }
}


// ============================================================
// TAPA SUPERIOR
// ============================================================

module tapa_superior() {
    union() {

        // ----------------------------------------------------
        // Techo
        // ----------------------------------------------------

        translate([
            0,
            0,
            altura_mitad - pared
        ])
            cube([
                ancho,
                profundidad,
                pared
            ]);


        // ----------------------------------------------------
        // Mitad superior del lateral izquierdo
        // ----------------------------------------------------

        cube([
            pared,
            profundidad,
            altura_mitad
        ]);


        // ----------------------------------------------------
        // Mitad superior del lateral derecho
        // ----------------------------------------------------

        translate([
            ancho - pared,
            0,
            0
        ])
            cube([
                pared,
                profundidad,
                altura_mitad
            ]);


        // ----------------------------------------------------
        // Poste superior izquierdo
        // ----------------------------------------------------

        poste_longitudinal(
            x = margen_poste_x,
            z = altura_mitad - margen_poste_z,
            lado = "izquierdo",
            fijacion_vertical = "superior"
        );


        // ----------------------------------------------------
        // Poste superior derecho
        // ----------------------------------------------------

        poste_longitudinal(
            x = ancho - margen_poste_x,
            z = altura_mitad - margen_poste_z,
            lado = "derecho",
            fijacion_vertical = "superior"
        );


        // ----------------------------------------------------
        // Labios de alineación
        // ----------------------------------------------------

        if (usar_encastre) {

            // Labio izquierdo
            translate([
                pared,
                0,
                -altura_labio
            ])
                cube([
                    espesor_labio,
                    profundidad,
                    altura_labio
                ]);


            // Labio derecho
            translate([
                ancho - pared - espesor_labio,
                0,
                -altura_labio
            ])
                cube([
                    espesor_labio,
                    profundidad,
                    altura_labio
                ]);
        }
    }
}


// ============================================================
// SALIDA
// ============================================================

if (pieza == "inferior") {
    tapa_inferior();
}


if (pieza == "superior") {
    tapa_superior();
}


if (pieza == "conjunto") {
    tapa_inferior();

    translate([
        0,
        0,
        altura_mitad
    ])
        tapa_superior();
}


if (pieza == "separadas") {
    tapa_inferior();

    translate([
        ancho + 20,
        0,
        0
    ])
        tapa_superior();
}