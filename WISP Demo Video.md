

Start: 
The technical problem 
- Is not the models 


- Wildfires?
	- They cost the US, shrug, ... $ 500 billion last year. 
	- Other Fact. (global warming)
	- Mention something about *this* city.
	
- So why can't we predict them? 
	- Doing so would allow.. us to
		- 
		- 
- It's not models. Over the last few days we have found out that there is A LOT of complex models. 

- The problem is Data Scarcity. 
	- Frequenucy of collection such as satellites. 
	- A 10% error in just one parameter can make the model 1500%

That's why we built WISP:
- A recursively self-improving, GPU-accelerated, informational theoretically optimal, bayesian drone network. 
- In other words


So, what does that mean...? 

- Broad Overview (like a table of contents of the purpose of each part). 


Fundamental points:
- All proposed drone systems target identifying where the fire is. Ours predicts where it will be.
- Secondly: we 

- Because of this: each 



Load satellite, terrain and weather data

Prior: Nelson FMC + HRRR wind + LANDFIRE terrain

- Update prediction past on all observations, scaled so that older predictions decay in relevance. 



-> Nelson Model: Generate Initial Prior prediction for 

The result: 
- A live stream of data 
- 


Why doesn't this exist if it is so good? 
- Well, ... we brought together a lot of technologies from different domains that werten't common within the domains. 

- Walking through each step and their engineering innovations (and benefits).

...

Steps to explore:
- First we compile all existing datatypes to create a broad estimate for the region, including satellite imagery, RAWS weather stations, 


- We compile
- Observation updates using a gaussian process which uses a lot of math. 

Go back to the initial prior: by the way, THIS is what current wildfires do. 

After doing this, we made it GPU accelerated:
- Allowing us to run 1000 parallel 8-hour predictions in less than two minutes on a single GPU.
- 


Other innovations: 







Key Innovations:
- Inspired by predictive processing model from cognitive science
- SOTA 
- Gaussian process regression from geostatistics
- Predictive

- Bayesian optimization from information theory
- 