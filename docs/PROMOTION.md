# Showing the project to the world — checklist & ready-to-paste posts

## Checklist
- [x] Repo public: https://github.com/Biraj17/traffic-system
- [x] MIT license
- [x] GitHub topics (sumo, traffic-simulation, machine-learning, openstreetmap, nepal, …)
- [x] README: headline, screenshots, ambulance GIF
- [ ] 2-min demo video (record with Cmd+Shift+5 following docs/DEMO_SCRIPT.md,
      upload to YouTube — unlisted is fine — link it at the top of README)
- [ ] Pin the repo on your GitHub profile (profile → Customize your pins)
- [ ] LinkedIn post (draft below)
- [ ] Share with OpenStreetMap Nepal / Kathmandu Living Labs
- [ ] College tech exhibition (LOCUS-style) / student conference paper

## LinkedIn post (edit freely, keep it in your own voice)

> Anyone who has crossed Kalanki at rush hour knows the wait. 🚦
>
> For my minor project I built an AI traffic signal controller and tested
> it on the REAL Kalanki Chowk — road geometry, buildings, even the Ring
> Road underpass, all imported from OpenStreetMap. Traffic is simulated in
> SUMO with Kathmandu's actual vehicle mix (45% motorbikes!) and
> pedestrians.
>
> Instead of a fixed timer, the controller reads every approach each cycle
> and computes green time with rules + a Random Forest model. Result,
> averaged over 5 randomized runs: **~80% less waiting and more vehicles
> through the junction** than a classic fixed timer. One button gives an
> ambulance a green corridor that clears itself after it passes.
>
> Everything runs on a laptop, open source (MIT):
> https://github.com/Biraj17/traffic-system
>
> Built with Python, SUMO, scikit-learn, and Streamlit.
> #Nepal #Kathmandu #TrafficEngineering #MachineLearning #OpenStreetMap

## Where else
- **OSM Nepal / Kathmandu Living Labs**: message their community channels —
  a real Kalanki use case of their map data is exactly what they showcase.
- **SUMO community**: the sumo-user mailing list and the Eclipse SUMO
  "powered by" showcase accept user projects.
- **Reddit**: r/OpenStreetMap or r/Python (lead with the GIF).
- **CV line**: "Adaptive AI traffic signal control on a real Kathmandu
  intersection (SUMO + scikit-learn) — cut average junction wait ~80% vs a
  fixed timer, validated across 5 random seeds."
