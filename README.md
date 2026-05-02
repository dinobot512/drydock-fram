# DRYDOCK 2026
## Fram
## NASA challenge

Add names:

* Dino Filipovic
* Dieu Truong
* Rae Kapitonova
* Jerald Arden Freeman
* Rutland Harri

## DELIVERABLES
* research
* analysis
* prototype
* software

### Phase 1
study about comms blackouts in wildfire common terrain
    quantify latency and dropout impacts on UTM deconfliction algo
analysis of existing UTM protocol and why its bad in this case
simulation environment (clud recommends matlab or discrete-event simulator) modelling crewed and UAS traffic over an evolving perimiter
proof of concept dynamic geofencing algorithm

### Phase 2
Software:

A working UTM extension module with a disconnected/degraded comms mode — aircraft carry onboard conflict detection logic so deconfliction doesn't collapse when the ground datalink drops
A common operating picture (COP) dashboard integrating live UAS feeds, fire perimeter overlays, and all aircraft positions for the incident command structure

Prototype:

A hardware-in-the-loop testbed demonstrating automated precision water drop coordination — UAS identifies hotspot via IR, passes coordinates, UTM reserves a corridor, tanker executes drop, all without voice radio coordination
A mobile PNT (position, navigation, timing) unit that provides GPS-independent localization for UAS in canyon terrain, validated against ground truth in a field test

## SUBTOPIC REJECTIONS!!!!!

DO NOT DO THESE!!!
* assisting with flight in bad conditions
* unmanned logistics
* wildfire suppression
* supporting management missions/ operations
