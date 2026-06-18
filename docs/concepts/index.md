# Introduction

## Three levels of abstraction

`technoeconomics-app` is designed to simplify technoeconomic analysis for all practitioners,
regardless of their programming skill. There are three levels at which you can interact with the
package:

1. Run pre-built analyses through a graphical user interface and command line interface. Vary costs of components, allowed CO2 emissions, enable and disable technologies, and much more. Gain intuition for the problem, and see what makes sense and what doesn't. No programming skill required.
2. Build your own analyses from reusable components developed by the community. We did the work of sourcing technoeconomic data, simulating renewable energy sources, and modelling technologies. You just snap components together. A new user can get started building custom models within an afternoon. Only basic programming skills required.
3. Build your own components and datasets - it's easier than you'd think! If you know what a `dataclass` is, and can write a script that returns a Pandas `Series` - you can build your own components. If you don't, we have tutorials to teach you :) `technoeconomics-app` does the heavy lifting of making sure your components work within the larger framework.

Documentation is also structured along those levels of abstraction:

- [Preset](./preset.md): how to use the various user interfaces to run pre-built presets -> how to build your own presets -> implementation details of the `Preset` class
- [Component](./component.md): descriptions of components available to build presets -> how to build your own components -> implementation details of the `Component` class
- [Data](./data.md): description of datasets that you can use in your components -> instructions for adding new ones -> implementation details of the `Dataset` class
- [Model](./model.md): deep dive into the way that models are built and implemented

## Design philosophy

The general philosophy between the design of `technoeconomics-app`:

- **opinionated and standardised** - we don't force you to choose between 20 different prices for a battery. There is always one way to do everything. We spend a lot of effort to make that way as good as it can be.
- **batteries included** - everything you need to build, run, and inspect models is contained within one package. You don't need to bring your own data, develop visualisations, or understand how to use an optimisation framework
- **flexible and powerful** - we provide clean, transparent abstractions and well defined interfaces. If you need to use a different dataset for something, or model a heat pump in a slightly different way - we make it easy for you to dig deep at any level of the stack.
