# Unmanned Aircraft System Traffic Management

Collaborative ecosystem

to our case UTM provides:
* automated operations (no manual radio needed)
* realtime awareness is shared between all users
* UAS integration - handles mixed mixed crewed/uncrewed traffic


They want us to extend UTM to be suitable for wildfire operations, which is at odds with how UTM was intended to be used.

UTM assumes:
* reliable datalinks - terrain blocks this
* predefined, static airspace structure
* GPS always working - terrain blocks

> static airspace zone - predefined volume that says who can operate in it and when
> drones cannot leave this area and are usually assigned to one specific flight

this presents an issue as zones declared one hour ago can be considered completely useless by the time drones get there. the safe volumes change and need to be regenerated in real time

> UAS surveillance - using unmanned aircraft as sensor platforms
> things UAS does:
> 1. visible light camera
> 2. thermal signatures (primary)
> 3. multispectral
> 
> periodically downlinks this data (for our estimates: 4hr)
>
> shares space with Air tankers, helicopters, air tactical supervisor
> traditionally, when these guys go out UAS gets grounded
> so make UTM good so these guys dont hit you
