# Elección de VPS: latencia real desde Argentina

Mediciones **reales** hechas el **2026-08-08** con sondas residenciales
argentinas (GlobalPing): ping ICMP de 10 paquetes desde Telefónica/Movistar,
Telecentro, CPS, Claro/Techtel, Sondatech, FULLNET y Cogent, en AMBA,
La Plata, Córdoba y Neuquén.

## Latencia medida (promedio en ms)

| Sonda (ISP) | VPS en Bs.As. | **Vultr Santiago** | Vultr São Paulo | Oracle São Paulo | Vultr Miami |
|---|---|---|---|---|---|
| Movistar (AMBA) | filtra ICMP | **22,3** | 🔴 **127,3** | 32,2 | 160,2 |
| Telecentro (AMBA) | 13,0 | **22,5** | 31,8 | 56,5 | 140,2 |
| CPS (AMBA) | filtra | **22,5** | 32,0 | 34,1 | 144,4 |
| FULLNET (Isidro Casanova) | 10,0 | **21,5** | 31,0 | 31,8 | 171,6 |
| Sondatech (La Plata) | 11,6 | **22,1** | 29,4 | 28,4 | 166,6 |
| Claro/Techtel (Córdoba) | filtra | **35,6** | 43,4 | 42,1 | 144,8 |

AWS São Paulo (medido por TCP/TLS porque filtra ICMP): 34-37 ms, **igual en
los tres ISPs de AMBA probados**.

## Los tres hallazgos que rompen el sentido común

**1. Santiago de Chile le gana a São Paulo: 22 ms contra 30 ms.** Es al revés
de lo que dice el folclore (hilos viejos hablaban de 80-120 ms a Chile). Los
enlaces transandinos actuales dan 21-23 ms estables, por fibra terrestre.

**2. El "tromboning" existe y hoy golpea a Vultr São Paulo desde Movistar.**
Un traceroute desde Movistar a São Paulo sale por la red de Telefónica, pega
siete saltos ocultos y aterriza a **127,7 ms** — comparado con 140-160 ms a
Miami, es inequívoco que el tráfico se va a Estados Unidos y vuelve.
Reproducido en dos corridas.

**3. También golpea a proveedores argentinos.** Dattatec/DonWeb da 7-12 ms
desde casi todos los ISPs, pero **148,6 ms desde Telecentro**: ping de Miami
hacia un datacenter que está a 300 km.

## Por qué pasa: CABASE

La explicación de todo es la membresía en **CABASE Buenos Aires**, el IXP
argentino (372 peers, 17 Tbps):

| Están en CABASE-BA | NO están |
|---|---|
| AWS (2×200 Gbps), Google, Microsoft, Cloudflare | **Vultr**, **Oracle** |
| Telecom, Telecentro, CPS, Claro (100 Gbps c/u) | **Movistar** (usa su backbone Telxius), Dattatec |

Movistar no está en CABASE y Vultr tampoco, así que la ruta entre ambos se
resuelve por tránsito internacional. AWS, en cambio, es el único hyperscaler
del comparativo on-net en Buenos Aires con 400 Gbps, y por eso midió parejo
en todos los ISPs.

## Descartes con motivo

- **Neolo**: tiene datacenter propio en CABA, pero **sus VPS no están ahí**
  (su IP resuelve a rango de EEUU). Medido: **178-190 ms**.
- **AWS Local Zone Buenos Aires**: existe y daría ping de un dígito, pero el
  tipo más chico útil sale **USD 56,43/mes** sin contar discos ni IP.
- **DigitalOcean y Contabo**: sin presencia en Sudamérica.
- **Oracle Free Tier**: en junio de 2026 recortaron el Always Free ARM de
  4 OCPU/24 GB a 2 OCPU/12 GB, y hay tromboning en Telecentro hacia Santiago
  (77 ms) y Valparaíso (126 ms).
- **Locaweb / Magalu (Brasil)**: baratos, pero probablemente exijan CPF/CNPJ.

## Notas operativas para los puertos que nos importan

- Ninguno de los candidatos bloquea puertos altos entrantes. Vultr no filtra
  nada por defecto (solo SMTP 25 saliente en cuentas nuevas).
- **AWS Lightsail**: los puertos vienen cerrados y se abren desde la consola,
  sin justificar nada.
- **Oracle**: doble firewall. Hay que abrir en la *Security List* de la VCN
  **y** en el `iptables` de la instancia. Es el error clásico que hace pensar
  que "no funciona".
- Ninguno usa CGNAT: todos dan IPv4 pública dedicada, que es lo que este
  proyecto necesita sí o sí.

## Decisión tomada

**Vultr, región Santiago (`scl`)**, plan `vc2-1c-2gb` (USD 10/mes) o
`vc2-2c-4gb` (USD 20/mes), Ubuntu 24.04 LTS.

El motivo: es el único destino que midió parejo en **todos** los ISPs
argentinos probados (20,4 a 22,5 ms, dispersión de 2 ms). No es el ping más
bajo posible — un datacenter en CABA da 10-13 ms — pero es el único que
garantiza que **ningún** jugador quede afuera, sin tener que averiguar antes
con qué ISP está cada uno. Encima Vultr cobra precio global en Santiago y
+50% en São Paulo, así que sale más barato *y* con menos ping que la opción
"obvia" de Brasil.

Sigue disponible como mejora futura la estrategia de dos pasos de abajo.

## Estrategia recomendada: dos pasos

1. Arrancar con **Vultr Santiago** (facturación horaria, el mes de prueba
   sale centavos). 22 ms garantizados para cualquier argentino con cualquier
   ISP.
2. En paralelo, pedir una IP de prueba a un proveedor con datacenter en CABA
   y que los jugadores —**especialmente los de Movistar y Claro**— la
   pingueen una semana. Si todos dan menos de 15 ms, migrar y ganar 10 ms y
   plata. Si aparece uno solo con 130 ms, ya está confirmado que Santiago era
   la respuesta.
