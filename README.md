# Attack-04 — DHCP Starvation (Pool Exhaustion)

> **Autor:** Julio Pujols  
> **Matrícula:** 20250692  
> **Red asignada:** 192.168.92.0/24  
> **Video demostrativo:** <https://youtu.be/j4qdjMDIuMI>

-----

## 1. Objetivo del Laboratorio

Demostrar el ataque **DHCP Starvation** agotando el pool de IPs del servidor DHCP
(R1, 192.168.92.1) mediante DISCOVERs con chaddr aleatorios, dejando sin servicio a
clientes legítimos, y mitigarlo con DHCP Snooping en un entorno de laboratorio aislado
sobre PNETLab + vIOS-L2.

-----

## 2. Objetivo del Script

`dhcp_starvation.py` genera y envía DHCP DISCOVERs continuos con chaddr (client
hardware address) aleatorio en cada paquete. El servidor DHCP asigna un lease
diferente por cada chaddr, agotando el pool disponible.

### 2.1 Parámetros

|Parámetro     |Descripción                       |Ejemplo|
|--------------|----------------------------------|-------|
|`-i / --iface`|Interfaz de red                   |`eth0` |
|`-r / --rate` |DISCOVERs por segundo (default: 5)|`10`   |
|`-c / --count`|Total a enviar (0 = infinito)     |`250`  |

### 2.2 Requisitos

|Requisito  |Versión     |
|-----------|------------|
|Python     |3.6+        |
|Scapy      |>= 2.4.0    |
|SO         |Linux / Kali|
|Privilegios|root / sudo |

```bash
pip install -r requirements.txt
```

-----

## 3. Funcionamiento del Script

### Flujo de ejecución

```
1. Parseo de argumentos, handler SIGINT
2. Bucle principal:
   a. _rand_mac_bytes() → 6 bytes aleatorios = chaddr único
   b. _build_discover(chaddr) → DISCOVER completo
   c. sendp() → envío L2 directo
   d. sleep(1/rate) → control de velocidad
3. Al interrumpir: estadísticas finales
```

### Estructura del paquete

```
[ Ether src=rand_mac dst=ff:ff:ff:ff:ff:ff ]
  └─[ IP src=0.0.0.0 dst=255.255.255.255 ]
      └─[ UDP sport=68 dport=67 ]
          └─[ BOOTP op=1 chaddr=<6_bytes_random> xid=<random> ]
              └─[ DHCP message-type=discover ]
```

### Por qué funciona

```
R1 (DHCP server) recibe DISCOVER:
  → extrae chaddr → no existe en bindings → asigna nueva IP del pool
  → pool 192.168.92.11–254 = 244 IPs
  → 244 DISCOVERs únicos agotan el pool completamente
  → siguiente cliente legítimo: sin IPs disponibles → DoS
```

-----

## 4. Documentación de la Red

### Topología

```
        R1 — 192.168.92.1/24 (DHCP server)
        DHCP pool: 192.168.92.11 – 192.168.92.254
              |
        SW1 ── Gi0/1 ── Attacker (Kali) → envía DISCOVERs
             ── Gi0/2 ── Victim1 → intenta obtener IP (DoS)
```

### Direccionamiento e interfaces

|Dispositivo|Interfaz|IP/Máscara     |VLAN  |Rol                        |
|-----------|--------|---------------|------|---------------------------|
|R1         |Gi0/0   |192.168.92.1/24|10    |DHCP server                |
|SW1        |Gi0/0   |—              |10 acc|Uplink a R1 (trusted)      |
|SW1        |Gi0/1   |—              |10 acc|Puerto atacante (untrusted)|
|Attacker   |eth0    |192.168.92.x   |10    |Atacante                   |
|Victim2    |e0      |sin IP (DoS)   |10    |Víctima (VPCS)             |

### Configuración DHCP en R1

```
ip dhcp excluded-address 192.168.92.1 192.168.92.10
ip dhcp pool LAN
 network 192.168.92.0 255.255.255.0
 default-router 192.168.92.1
 dns-server 192.168.92.1
```

-----

## 5. Ejecución

### Estado inicial

```
R1# show ip dhcp pool        ! Available: 244
R1# show ip dhcp binding     ! (vacío)
```

### Ejecutar el ataque

```bash
sudo python3 dhcp_starvation.py -i eth0 -r 5
```

### Verificar impacto

```
R1# show ip dhcp pool        ! Available: 0 — pool agotado
R1# show ip dhcp binding     ! cientos de leases con MACs aleatorias

! Victim2 (VPCS): ip dhcp → no obtiene IP
```

-----

## 6. Contramedida

### Mecanismo

**DHCP Snooping** con rate-limit restringe la cantidad de mensajes DHCP por segundo
desde puertos no confiables. El comando `no ip dhcp snooping information option` es
necesario para que R1 (servidor en la misma red) procese DHCP correctamente sin
rechazar paquetes por la inserción de Option 82.

### Configuración en SW1

```
SW1(config)# ip dhcp snooping
SW1(config)# ip dhcp snooping vlan 10
SW1(config)# no ip dhcp snooping information option
!
SW1(config)# interface GigabitEthernet0/0
SW1(config-if)# ip dhcp snooping trust
SW1(config-if)# exit
!
SW1(config)# interface GigabitEthernet0/1
SW1(config-if)# no ip dhcp snooping trust
SW1(config-if)# ip dhcp snooping limit rate 10
SW1(config-if)# end
SW1# write memory
```

### Verificación

```
SW1# show ip dhcp snooping
SW1# show ip dhcp snooping statistics
! "DHCP messages dropped" sube con el ataque activo

R1# show ip dhcp pool
! Available no baja a 0 — pool protegido

! Victim2: ip dhcp → obtiene IP correctamente
```

-----

## 7. Conclusiones

Este ataque me enseñó algo importante sobre el orden de las cosas en el laboratorio. Al principio el ataque no funcionaba y no me llenaba el pool, y después de revisar me di cuenta de que el Port Security que había configurado en el ataque anterior seguía activo en el puerto del atacante y estaba bloqueando las MACs aleatorias que generaba el script. Aprendí que tengo que limpiar las contramedidas de un ataque antes de pasar al siguiente para que las pruebas sean válidas.

## Una vez resuelto eso, vi cómo el pool de R1 bajaba hasta quedar en 0 direcciones disponibles y cómo Victim2 ya no podía obtener una IP. Al configurar DHCP Snooping con rate-limit también me topé con que R1 dejaba de entregar direcciones, y descubrí que el problema era la inserción de la opción 82 en los paquetes; al agregar `no ip dhcp snooping information option` todo volvió a funcionar correctamente. Con esto entendí que DHCP Snooping no solo sirve contra el starvation, sino que además es la base sobre la que se apoyan otras protecciones como DAI.

## 8. Referencias

- RFC 2131 — Dynamic Host Configuration Protocol
- Cisco DHCP Snooping Configuration Guide
- Scapy DHCP/BOOTP: scapy.layers.dhcp
