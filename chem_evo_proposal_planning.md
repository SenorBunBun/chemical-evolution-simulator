**Legend:**

* **Properties** or **Parameters** or bolded  
* **\[**Text within brackets represents biological equivalence**\]** 

**Simulation Members:**

* Building Blocks \[Ions, Functional Groups, Monomers, etc.\]  
* Molecules (Composed of N “bonded” building blocks)  
* Assemblies (Composed of M H-bonded Molecules, Chance to be Catalytic)

**Chemical Properties**

**Building Blocks Properties \[SNOPS, Functional Groups, Monomers, etc.\]:**

* **Mobility \[Molecular Weight\] (int):** how much can this building block move by itself  
* **Formation Reactivity (Nucleophilicity/Electrophilicity) \[int\]:** Chance this block will form a bond with another on contact  
* **Breaking Reactivity (Hydrolysis Resistance)  \[int\]:** A numerical property representing how resistant bonds formed with this block are to hydrolysis. Probability of breaking a bond at a timestep is the average of its 2 constituents.  
* **Hydrogen\_bond\_type:** Must be H-bond donor or acceptor, plays a role in assembly formation  
* **Latent\_catalytic\_potential :** A randomly assigned property that determines how catalytic an assembly will be based off the building blocks, rather than chance. Allows for more emergent selection.

**Molecular Properties:**

* **Mobility \[Molecular Weight\] (int)**: Average of all mobility of N building blocks composed of it, with a **molec\_mobility\_penalty** that scales with N, replacing building block mobility.  
* **Bonding is all Linear (Max 2 bonds per building block)**

**Catalytic Chance:** Probability that an assembly will become catalytic when first assembled or as molecules continue to add to the assembly 

**Assembly Properties:**

* **assembly\_bond\_resistance \[hydrolitic\_resistance\]:** penalty subtracted from probability of breaking bonds that are within the assembly  
* **Mobility \[Molecular Weight\] (int):** Average of the molecules that composed of it, subtract **assembly\_mobility\_penalty** for M  
* **Assembly\_chance:** Chance of assembly given **base\_assembly\_chance**, but scaled with matching N and M (molecules in assembly)  
* **Catalysis Properties:**  
  * **Catalysis\_score:** Score that controls two major functions. Sum of building blocks **latent\_catalytic\_potential** Scales with **M**  
    * Chance that in **catalysis\_range**, building blocks will be generated randomly  
    * Bonus chance of Formation Reactivity within **catalysis\_range**

The simulation can be summarized as building blocks bounce around, bond to each other, and then when they reach a certain size they can assemble if H-bond types are fully corresponding. Then, every time an assembly grows and is made, there is a chance to be a catalyst, which is determined by the latent properties in the building block. 

**Simulation Rules**

**Setup:**

* Grid where all building blocks are placed with randomly generated properties  
* All members constituents will move around in a random direction based on their mobility every timestep  
* As blocks move around and collide, each collision event will be the main logic of how bonds are made, and assemblies are made.   
* Currently, we will have a fixed amount of molecules determined at the beginning.

**At each time step:**

* Members move with velocity proportional to their mobility

* **Breaking Bonds:**  
  * All bonds have a chance of breaking according to the average of **Breaking Reactivity** of its 2 constituents, if both constituents are participating in a H-bond, this chance is reduced by an **assembly penalty** (represents hydrolysis resistance in an assembly)

* Rules Governing Collisions  
* Additional rules

* **Catalysis Formation:**   
  * If assemblies form or are added to, only then there is probability of **catalysis\_chance** they will become catalytic (occurs after the collision is handled)

**Collision & Other SImulation Rules \[Formation of Bonds & H-bonded Assemblies\]:**

**(Rule) Collision Logic occurs when a building block is within 1 a set distance (same as bond length) of another building block**

**(Rule) Objects that are bonded or assembled with one another move together as a unit, no inter-assembly/molecule movement**

**(Rule) Bonding is linear,** Building Blocks cannot have more than 2 other blocks attached to it.

**(Rule) Only when building blocks collide can bonds or assemblies form**

**(Rule) Building Block \+ Building Block (No assemblies):**

* If building blocks both have less than 2 other blocks attached:  
  * **Probability of forming bond:** Average of blocks’ **Formation Reactivity**  
* Occurs if building blocks are in molecules, assemblies etc.

**(Rule): Molecules of N\<5 cannot assemble.** We are assuming IMF’s are negligible until our molecules grow enough.

**(Rule) Assembly Formation:** Assemblies can only form if the molecule colliding with said molecule has **fully matching donor/acceptor pairs (D to A, A to D)**. 

**(Rule) Assembly Formation Extended**: Let’s say Mol A collides with Mol B and Mol B is already assembled with Mol C. If an assembly chance occurs and Mol B is already H-bonded on both sides, which molecule joins the assembly given to the molecule with higher N. If Mol A has a larger N, Mol C  is removed from assembly. If not, nothing happens. Partial matches are not allowed for simplicity.

**(Rule) Collisions where Assembly & Bonding are both possible (H-bond types match, bonds available):**

* If both assembly and bonding are allowed, the resulting possibilities are now weighted by chance  
* Weighted Random Chance of:   
  * Avg(Average of blocks touching **Formation Reactivity**  
  * **Assembly Chance** (read properties)

**(Rule) Collisions where only Assembly is Possible (H-bond types match):** 

* Chance of assembly is **Assembly Chance**  
* This will often happen in the middle of the assembly, and the edges will be able to bond more readily

**(Rule)  Bonds that don’t participate in H-bonding, do not get assembly protection against hydrolysis.** 

**(Rule) Single Building Blocks cannot participate in H-bonding.** 

(**Rule) When Assemblies are Made, They are made flat.** This saves expensive logic for handling matching custom shapes, and can easily be expanded on later. This still preserves the core of the simulation logic. Molecules can bounce around and bond in the general direction they collide in, but when assemblies are made they are flattened into lines.

---

**Intentional Design Choices (For Simplicity):**

* Many of our rules preventing things, can be simply replaced with probabilities that scale with certain factors  
* No Wet-dry cycling  
* Our catalysts are asymmetric and are all constructive  
  * Essentially, in experimental results at the Williams Lab catalysts act asymmetrically during phases of the wet-dry cycle, only being constructive or destructive in one part of the cycle. We assume all our catalysts to be constructive for now. We can add switching behavior for wet-dry cycling  
* No solubility  
* Can Potentially test adding molecules rather than a fixed amount, but not within scope  
* Partial matches are not allowed for simplicity (can be added later), as would need to have several parameters governing replacing assemblies as well as the breaking of assemblies, and penalties for partial matches and where the “match” occurs  
* For now, our main driving force for supporting H-bonds is that non H-bonded molecules do not have hydrolysis protection.   
* Although molecules are allowed to have structure, we will make assemblies flat (essentially like a line) as logic to resolve novel shapes is beyond scope

---

**Implementation Details**

**Overarching Implementation:**

Implementation-wise this is a particle system with rigid body constraints:

Each building block stores its own position. Each molecule/assembly stores a list of its block IDs and their relative offsets from the anchor point. Movement applies one velocity to the anchor, all blocks follow. Collision could possibly use spatial hashing on individual block positions. Pygame draws circles for blocks and lines for bonds.Whatever makes sense. 

**Default Initialization;**

* \# of building blocks, randomly generated properties   
* Spread across the grid randomly  
* Initial movement vectors also random

**Bond formation:**

When bonds are made, bond length is the same length as collision radius, because when somewhere in an assembly a bond is broken, if the assembly still is all connected rigidly, then that bond can just “collide “and reform as it is being supported by the assembly. Catalysts ranges should be colored most likely as well. 

When assemblies are made or added to, ensure the flatness of the thing being attached to.

**Visuals:**

One color for building blocks, that can be color coded if needed based on certain properties, bonds is one color. H-bonds are another, etc. catalysts can be highlighted differently, having a border of some kind maybe. Color-coding might be useful. Bonds should be colored too by their strength, you know.

Clean interface, fast & processing. pausing , watching, fast forwarding. 

Maybe live graphs being made on the side, or definitely various properties throughout time graphs. That data needs to be accessible for sure or at least maintained during the simulation like \[Average N for t=0, t=1, ……\] and then some other properties as well. 

**Computationally what’s required to be checked often:**

**On Collision (readily):**

* **Bond formation:** Is a building block available to bond? (Number of bonded constituents)  
* **Total Number N for both things collided**  
* If N\>5, full H-bond type string in the molecule to see if the strings correspond. (Check if assembly is possible). N of the current molecule needs to be also easily checked as well, as it needs to match.  
* If it's within range of a catalyst for the bonus.

**On timesteps:**

* All bonds and their weighted average of hydrolysis breakage for hydrolysis timestep  
* Rigid Body groupings. What is attached to what, as bonded things have to be rigid and just move with one velocity, these can break but remember it might break but still be H-bonded so it's still rigid. Essentially, cases where bonds break but it is still one rigid body.  
* If something is catalytic, have a chance to generate when at the same\_freq as hydrolysis, can be another parameter

**Velocity Implementation:** 

On movement, persistent velocity with bouncing (billiard balls)

Give each entity a velocity vector (direction \+ speed proportional to mobility). Each timestep, it moves along that vector. When it hits a wall, reflect the velocity. When it hits another entity, collision logic triggers and both get deflected if no bonds are made. If bonds are made, velocities are summed. This is basically billiard ball physics and it looks great visually — things drift, bounce off walls, ricochet off each other. Much more natural than random direction picks each timestep.

**Bond Breaking:** 

When a bond breaks in the middle of a chain, if we now have two separate rigid bodies. Give each fragment a separate direction, and let mobility decide the rest. so they visually drift apart. With linear bonding (max 2 bonds per block), a break always cleanly splits a molecule into two pieces — there's no ambiguity about which blocks belong to which fragment. 

When a bond breaks inside an assembled molecule, split the molecule record into two fragment records but keep both in the assembly's member list with their existing H-bond connections unchanged. No special logic needed beyond the split itself. This allows the velocity to still act on the whole assembly.

Once a bond breaks, check if either of the two bonds become single building blocks N=1 that are H-bonded, we need those to also not exist. 

**Other Key Features:**

Having JSON config files for all parameters, representing the number of time steps for an auto-run, etc. Doesn’t always auto-run. Set the amount of particles in the beginning.

Can make hydrolysis chances happen every X timesteps. 

Needs also need master settings, where I can give an example scenario and see how that would look. Grid velocities so I can test out collisions during debugging. 

Easily scale up molecules, building block, assembly properties and rules (as well as catalysis). Might expand that later, etc. This all should be very scalable.

Implementation Order:

1. Molecules bouncing, bonds forming, bonds breaking, visuals stopping and starting, just based on those factors. All properties built and framework all laid out with assembly classes etc., but just the molecules and that logic working first. Bond visualizations etc. Generation of the randomly distributed molecules. Color-coding should be implemented in the beginning actually, like color building blocks based on reactivity of formation and each bond by Avg(Breaking reactivity). As well as “god features” for debugging, allowing to set up scenarios.  
2. Adding assembly logic, testing  
3. Ensuring more complex color-coding is working and then add and test catalysis logic.  
4. Adding more complex graph logic (live maybe), or color-coding during the simulation etc.
