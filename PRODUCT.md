# SABZ product architecture

The supported product foundation is now the `sabz_edge` package. Start with
[the integration guide](docs/INTEGRATION.md), [security scope](SECURITY.md) and
[release roadmap](docs/ROADMAP.md).

The edge service receives authenticated observations, persists replay watermarks,
and runs a timed two-phase controller independently of HTTP request frequency.
All outputs target a bench emulator. The live camera script is an observation
producer using the same API. Physical cabinet integration and field approval
remain explicit release gates.

Historical scripts and models are research artifacts. Online controller
exploration, automatic nightly model promotion and LLM control are not enabled
in this integration release.
