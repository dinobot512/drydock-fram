
-Stakeholders-
1. Incident Commander
- map
	- fire simulation 
	- position of all units
	- status of all units (online/offline)
	- current mission of all units
- control over all units
- given decision support tools
- emergency alerts

2. Air Dispatch
- control over all UAS
- control over manned aircraft
- multi-mission planning tools

3. Manned Aircraft Pilot
- position and direction of all UAS
	- can send signals to drones to move away
- fire perimeter data
- all ground crew positions
- decision tools - ie. optimized water drop locations

4. Ground Crew
- most updated fire perimeter data
	- incl some high level data collected by drones in real time
- rescue alerts
- awareness of aircraft operations



-Mesh Network-
- Nodes consist of UAS, Manned Aircraft, and Ground Crew
- Nodes closest to command center serve as mediators between the command and the rest of the network

The drones, ground crew radios, and aircraft all have radios that are constantly broadcasting a beacon — essentially saying "I'm here, I'm reachable." When two nodes get close enough, they hear each other's beacon and form a link. The mesh protocol then advertises routes — "I can reach UAS-03, and UAS-03 can reach GROUND-02, so if you need to talk to GROUND-02, send it through me." As nodes move, links form and break, and the routing table updates automatically. The radios would be like those from Silvus Technologies, which provide up to a few km in NLOS (no line of sight) conditions.



-Drone Architecture-

Offline Operations:
- stores (most recent) map containing current fire location, spread prediction
- stores (most recent) adjacent drone node locations 
	- stores routing table, which lists all the nodes it is connected to and all the nodes those are connected to - this allows to send information through most efficient path
- stores (most recent) assigned instructions and/or movement path & follows it
- records data (fire edge location, humidity, wind speed) with timestamp and location coordinates
- creates a queue of data to be shared with other network nodes, assigns different priorities to different data
- sends out continuous signal to search for nodes nearby


Mesh operations (when a connection to one or modes nodes is established):
- send data to adjacent nodes according to queue priority
- update routing table
- receive data from adjacent nodes
- look out for any override instructions from manned aircraft nodes
- modify path to avoid intersecting manned aircraft nodes
- avoid other UAS nodes


Online Operations:
- share data with control center, receive instructions
- sync all known information across the network
- implement algorithm to choose which nodes have priority in overriding data over other nodes




























