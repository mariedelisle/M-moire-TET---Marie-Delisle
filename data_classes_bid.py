from dataclasses import dataclass

import numpy as np
import pandas as pd

@dataclass
class Turbine:
    """
        Abstract base class representing a hydroelectric turbine.

        This class defines the common interface shared by all turbine
        implementations used throughout the hydraulic simulation model.

        A turbine converts water into electrical energy. Depending on the
        power plant, the hydraulic characteristics, the reservoir level,
        and the operating constraints, each turbine uses its own calculation
        methods. For this reason, all physical computations are delegated
        to specialized subclasses.
        """
    # Unique identifier of the turbine.
    name: str

    # Time series containing turbine power values.
    power: pd.DataFrame | None = None

    # Natural inflows associated with the turbine or its catchment.
    natural_inflows_df: pd.DataFrame | None = None

    # Maximum installed generating capacity of the turbine (MW).
    maximum_power: float | None = None

    # Minimum operating power threshold (MW).
    minimum_power: float | None = None

    # Mandatory environmental flow that must remain in the river
    # downstream of the facility (m³/s).
    instream_flow: float | None = None

    # Time series describing equipment unavailability coefficients.
    unavailability_df: pd.DataFrame | None = None

    # Hydraulic node connected to the turbine and providing
    # incoming water flows.
    node: object | None = None

    # Reservoir associated with the turbine.
    reservoir: object | None = None

    # First timestamp of the simulation horizon.
    start_date: pd.Timestamp | None = None

    def efficiency(self, date, next_date):
        """
        Compute the turbine efficiency coefficient.

        The efficiency coefficient, also referred to as the hydraulic
        conversion coefficient K, links water flow to electrical power
        production.

        Hydraulic efficiency coefficient expressed in MW/(m³/s).
        """
        raise NotImplementedError("Each turbine must define its efficiency")

    def reference_efficiency(self, date, next_date):

        raise NotImplementedError("Each turbine must define its efficiency")

    def unavailabilities(self, date, next_date):
        """
        Retrieve the turbine unavailability coefficient.

        The coefficient represents the fraction of installed capacity
        unavailable because of maintenance, outages, or operational
        restrictions.
        """
        raise NotImplementedError("ach turbine must define its unavailabilities")

    def inflows(self, date, next_date):
        """
        Retrieve the hydraulic inflow associated with the turbine.
        """
        raise NotImplementedError("Each turbine must define its inflows")

    def maximum_inflows(self, date, next_date):
        """
        Retrieve the maximum flow that can be turbined.

        This value is generally constrained by turbine capacity,
        hydraulic conditions, and equipment availability.
        """
        raise NotImplementedError("Each turbine must define its maximum inflows")

    def turbined_inflows(self, date, next_date):
        """
        Retrieve the actual volume of water passing through the turbine.
        """
        raise NotImplementedError("Each turbine must define its turbined inflows")

    def maximum_corrected_power(self, date, next_date):
        """
        Compute the available maximum generation capacity.

        The theoretical maximum power may be reduced by maintenance,
        outages, or other operational constraints.
        """
        raise NotImplementedError("Each turbine must define its corrected maximum power")

    def sliding_outflow(self, date, next_date):
        raise NotImplementedError("Castet turbine must define its sliding outflow")

    def optimal_outflow(self, date, next_date):
        raise NotImplementedError("Castet turbine must define its optimal outflow")

    def coefficient_castet(self, date, next_date):
        raise NotImplementedError("Castet turbine must define its coefficent for optimal outflows")

    def compute_power(self, date, next_date):
        """
        Retrieve electrical power generation.
        """
        raise NotImplementedError("Each turbine must define its power")

class MiegebatTurbine(Turbine):

    def __init__(self, *args, **kwargs):
        """
        Initialize the internal state of the Miegebat turbine.

        Several intermediate values are stored between timesteps to:
        - avoid unnecessary efficiency recalculations,
        - reproduce the behaviour of the reference Excel model,
        - preserve the efficiency value used from Day 2 onward.
        """

        super().__init__(*args, **kwargs)

        self.previous_turbined_inflows = None
        self.previous_efficiency = None
        self.eff_j2_h1 = None

    def efficiency(self, date, next_date):
        """
        Compute the hydraulic efficiency coefficient K of the Miegebat turbine.

        Unlike the upstream turbines, the Miegebat efficiency is determined
        directly from the turbined flow using an empirical performance curve.

        To reproduce the historical operational model, the efficiency
        calculated during the last hour of Day 1 is stored and reused from
        Day 2 until the end of the simulation horizon.

        Hydraulic conversion coefficient K (MW/(m³/s)).
        """
        day2_start = self.start_date + pd.Timedelta(days=2)

        # Reuse the Day-1 reference efficiency for the remainder
        # of the simulation horizon.
        if date >= day2_start and self.eff_j2_h1 is not None:
            return self.eff_j2_h1

        # This represents the water flow actually turbined by the Miegebat turbine.
        turbined_inflows = self.turbined_inflows(date, next_date)

        # Empirical flow-efficiency relationship derived from
        # the Miegebat operating curve.
        flow_values = np.array([
            -1.00, 0.00, 2.47, 3.27, 4.17, 4.81, 5.66,
            6.43, 7.79, 11.89, 14.21, 16.49, 17.95,
            19.52, 20.94, 22.69, 24.50
        ])
        eff_values = np.array([
            0.000900, 0.000900, 0.000900, 0.000900,
            0.000900, 0.000900, 0.000900,
            0.000900, 0.000900, 0.000884,
            0.000875, 0.000866, 0.000861,
            0.000856, 0.000852, 0.000847,
            0.000842
        ])

        def efficiency_miegebat_flow(flow):
            """
            Retrieve the hydraulic efficiency coefficient associated
            with a given turbined flow.
            """

            # Enforce the minimum operating flow considered by the model.
            flow = max(flow, 2)

            # Stepwise lookup reproducing the original Excel implementation.
            idx = np.searchsorted(flow_values, flow, side="right") - 1
            idx = max(idx, 0)

            return eff_values[idx]

        # Compute the initial efficiency value.
        if self.previous_turbined_inflows is None:
            efficiency = efficiency_miegebat_flow(turbined_inflows)

        # Reuse the previous efficiency when hydraulic conditions
        # remain unchanged.
        elif turbined_inflows == self.previous_turbined_inflows:
            # Reuse previous efficiency value to avoid unnecessary recalculation
            efficiency = self.previous_efficiency

        else:
            # Recompute the efficiency when the turbined flow changes.
            efficiency = efficiency_miegebat_flow(turbined_inflows)

        # Store the efficiency reference used from Day 2 onward.
        if date == day2_start - pd.Timedelta(hours=1):
            self.eff_j2_h1 = efficiency

        # Preserve the current state for the next timestep.
        self.previous_turbined_inflows = turbined_inflows
        self.previous_efficiency = efficiency

        # Return the hydraulic coefficient K for the current timestep
        return efficiency # (MW/(m3/s))

    def unavailabilities(self, date, next_date):
        """
        Retrieve the turbine unavailability coefficient.
        """

        coefficient = self.unavailability_df["valeur"].asof(date)

        # Check if a valid value exists (i.e. not NaN)
        if pd.notna(coefficient):
            return coefficient

        else:
        # If there is no value we assume that the turbine is fully available
            return 0

    def maximum_inflows(self, date, next_date):
        """
        Compute the maximum flow that can be turbined.

        The available generating capacity is converted into an equivalent
        hydraulic flow using the Miegebat efficiency curve.

       Maximum admissible turbined flow (m³/s).
        """

        # Retrieve maximum available power (MW), corrected for unavailability
        maximum_corrected_power = self.maximum_corrected_power(date, next_date)

        # If available power is too low → turbine is considered off
        if maximum_corrected_power < 0.1:
            return 0

        # Empirical table
        # relationship between power (MW) and hydraulic coefficient K
        power_values = np.array([
            0, 0,
            8, 11, 14, 16, 19, 21,
            26, 40, 48, 55, 59, 63, 67, 71, 75
        ])

        eff_values = np.array([
            0.000900, 0.000900,
            0.000900, 0.000900, 0.000900, 0.000900,
            0.000900, 0.000900,
            0.000900, 0.000884, 0.000875, 0.000866,
            0.000861, 0.000856, 0.000852, 0.000847, 0.000842
        ])

        # Ensure non-negative power
        power = max(maximum_corrected_power, 0)

        # Interpolate K value based on power
        #efficiency = np.interp(power, power_values, eff_values)
        idx = np.searchsorted(power_values, power, side="right") - 1
        idx = max(idx, 0)

        efficiency = eff_values[idx]

        # Safety check to avoid division by very small values
        if efficiency <= 1e-8:
            return 0

        # Convert maximum power (MW) into maximum turbine flow (m3/s)
        # using K and hourly timestep conversion (1 hour = 3600 s)
        return maximum_corrected_power / (efficiency * 3600)

    def turbined_inflows(self, date, next_date):

        """
        Compute the effective flow passing through the turbine.

        The incoming flow is reduced by the mandatory environmental
        flow requirement and capped by the turbine hydraulic capacity.

        Effective turbined flow (m³/s).
        """

        # Total inflow arriving at the Miegebat node (from upstream turbines, natural inflows, etc.)
        inflows_node = self.node.inflows(date, next_date)

        # Maximum turbine flow capacity
        maximum_inflows = self.maximum_inflows(date, next_date)

        # Compute the actual turbinated flow:
        # - subtract the reserved flow (minimum environmental flow that must remain in the river)
        # - limit by the turbine capacity
        # - ensure non-negative flow
        turbined_inflows = max(
            0,
            min(inflows_node - self.instream_flow, maximum_inflows)
        )

        return turbined_inflows

    def maximum_corrected_power(self, date, next_date):
        """
        Compute the maximum power available after applying
        turbine availability constraints.

        Available generation capacity (MW).
        """

        # Retrieve turbine unavailability rate (between 0 and 1)
        unavailabilities = self.unavailabilities(date, next_date)

        # Compute corrected maximum power:
        # - If the turbine is fully available → full capacity (Pmax)
        # - If partially unavailable → reduce capacity proportionally
        # (1 - UN) represents the available fraction of the turbine
        corrected_maximum_power = min(
            self.maximum_power,
            (1 - unavailabilities) * self.maximum_power
        )

        # Return corrected maximum power
        return corrected_maximum_power #(MW)

    def compute_power(self, date, next_date):
        """
        Compute the electrical production of the Miegebat turbine.

        Power generation is calculated from the turbined flow and
        the hydraulic coefficient K:

            Power = Flow × K × 3600

        The resulting production is constrained by:
        - turbine availability,
        - installed capacity,
        - minimum operating threshold,
        - legacy dispatch rules inherited from the original Excel model.

        Electrical power production (MW).
        """

        # Retrieve hydraulic and operational inputs.

        turbined_inflows = self.turbined_inflows(date, next_date)
        efficiency = self.efficiency(date, next_date)

        maximum_power = self.maximum_corrected_power(date, next_date)
        minimum_power = self.minimum_power

        # upstream powers
        power_artouste = self.node.artouste.power["valeur"].asof(date)
        power_bious = self.node.bious.power["valeur"].asof(date)
        power_fabreges = self.node.fabreges.power["valeur"].asof(date)

        # sécurités
        power_artouste = 0 if pd.isna(power_artouste) else power_artouste
        power_bious = 0 if pd.isna(power_bious) else power_bious
        power_fabreges = 0 if pd.isna(power_fabreges) else power_fabreges

        # heure précédente (BC dans Excel)
        previous_date = date - pd.Timedelta(hours=1)

        # Upstream production used by the legacy dispatch rule.
        prev_artouste = self.node.artouste.power["valeur"].asof(previous_date)
        prev_bious = self.node.bious.power["valeur"].asof(previous_date)
        prev_fabreges = self.node.fabreges.power["valeur"].asof(previous_date)

        # Upstream production used by the legacy dispatch rule.
        prev_artouste = 0 if pd.isna(prev_artouste) else prev_artouste
        prev_bious = 0 if pd.isna(prev_bious) else prev_bious
        prev_fabreges = 0 if pd.isna(prev_fabreges) else prev_fabreges

        power_raw = turbined_inflows * efficiency * 3600

        power_capped = min(power_raw, maximum_power)

        # Apply the turbine minimum generation constraint.
        # The unit is assumed to be either fully operational or stopped;
        # intermediate production below the minimum technical power is not allowed.
        if power_capped < minimum_power:
            base_power = 0
        else:
            base_power = power_capped

        # Special dispatch rule reproduced from the historical Excel model.
        # This rule preserves a minimum production level at Miegebat during
        # specific upstream shutdown transitions in order to match the
        # operational behavior observed in the reference calculations.
        if (
                power_artouste <= 6
                and (power_bious + power_fabreges == 0)
                and (
                (prev_artouste + prev_bious + prev_fabreges) > 6
                or
                (prev_bious + prev_fabreges) > 0
        )
        ):
            return round(max(6, base_power), 1)

        return round(base_power, 1)

class HouratTurbine(Turbine):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previous_efficiency = None
        self.efficiency_memory = {}
        self.eff_j2_h1 = None
        self.previous_turbined_inflows = None

    def efficiency(self, date, next_date):
        """
        Compute the hydraulic efficiency coefficient K of the Hourat turbine.
        """

        start_date = self.start_date

        jour2_h1 = start_date + pd.Timedelta(days=2, hours=1)
        jour2_h2 = start_date + pd.Timedelta(days=2, hours=2)

        # Freeze efficiency from Day 2 Hour 2 onward
        if (
                self.eff_j2_h1 is not None
                and date >= jour2_h2
        ):
            return self.eff_j2_h1

        if date in self.efficiency_memory:
            return self.efficiency_memory[date]

        turbined_inflows = self.turbined_inflows(
            date,
            next_date
        )

        # Excel:
        # IF(FT_Hourat_T(h)<1.9,1.9,FT_Hourat_T(h))
        turbined_inflows = max(
            turbined_inflows,
            1.9
        )

        def efficiency_hourat_flow(flow):
            """
            Reproduction of:
            VLOOKUP(flow, K_variable!E99:G121, 3)
            """

            flow_values = np.array([
                -1.00, 0.00, 1.00, 2.00, 2.25,
                2.50, 3.00, 3.50, 4.00, 4.50,
                5.00, 5.50, 6.00, 8.00, 10.00,
                12.00, 14.00, 16.00, 18.00,
                20.00, 22.00, 24.00, 26.00
            ])

            efficiency_values = np.array([
                0.000000, 0.000140, 0.000157, 0.000173,
                0.000211, 0.000242, 0.000288, 0.000321,
                0.000345, 0.000386, 0.000419, 0.000446,
                0.000468, 0.000490, 0.000495, 0.000486,
                0.000477, 0.000487, 0.000492, 0.000490,
                0.000486, 0.000480, 0.000508
            ])

            idx = np.searchsorted(
                flow_values,
                flow,
                side="right"
            ) - 1

            idx = max(idx, 0)

            return efficiency_values[idx]

        # Jour 0 H1
        if self.previous_turbined_inflows is None:

            efficiency = efficiency_hourat_flow(
                turbined_inflows
            )

        # Excel :
        # IF(FT(h)=FT(h-1), Eff(h-1), ...)
        elif turbined_inflows == self.previous_turbined_inflows:

            efficiency = self.previous_efficiency

        else:

            efficiency = efficiency_hourat_flow(
                turbined_inflows
            )

        # Store Day 2 Hour 1 reference efficiency
        if date == jour2_h1:
            self.eff_j2_h1 = efficiency

        self.previous_turbined_inflows = turbined_inflows
        self.previous_efficiency = efficiency

        self.efficiency_memory[date] = efficiency

        return efficiency

    def reference_efficiency(self, date, next_date):

        day_start = date.normalize()

        efficiencies = []

        for hour in range(24):
            current_date = day_start + pd.Timedelta(hours=hour)
            current_next_date = current_date + pd.Timedelta(hours=1)

            efficiency = self.efficiency(
                current_date,
                current_next_date
            )

            efficiencies.append(efficiency)

        return np.mean(efficiencies)


    def unavailabilities(self, date, next_date):
        """
        Retrieve the turbine availability coefficient.

        Values are loaded from Hdx_data.
        """

        unavailabilities = (
            self.unavailability_df["valeur"].asof(date)
        )

        if pd.isna(unavailabilities):
            return 1

        return unavailabilities

    def maximum_inflows(self, date, next_date):

        maximum_corrected_power = self.maximum_corrected_power(
            date,
            next_date
        )

        if maximum_corrected_power < 0.1:
            return 0

        def efficiency_hourat_power(power):

            power_values = np.array([
                0.000000, 0.000000, 0.636344,
                1.272688, 1.747573, 2.222457,
                3.172225, 4.121993, 5.071761,
                6.383073, 7.694385, 9.005696,
                10.317008,
                14.390791,
                18.172541,
                21.444603,
                24.543405,
                28.609882,
                32.523872,
                36.002389,
                39.248830,
                42.298547,
                48.500000
            ])

            efficiency_values = np.array([
                0.000000,
                0.000140,
                0.000157,
                0.000173,
                0.000211,
                0.000242,
                0.000288,
                0.000321,
                0.000345,
                0.000386,
                0.000419,
                0.000446,
                0.000468,
                0.000490,
                0.000495,
                0.000486,
                0.000477,
                0.000487,
                0.000492,
                0.000490,
                0.000486,
                0.000480,
                0.000508
            ])

            idx = np.searchsorted(
                power_values,
                power,
                side="right"
            ) - 1

            idx = max(idx, 0)

            return efficiency_values[idx]

        efficiency = efficiency_hourat_power(
            maximum_corrected_power
        )

        if efficiency <= 1e-8:
            return 0

        return (
                maximum_corrected_power
                /
                (efficiency * 3600)
        )

    def turbined_inflows(self, date, next_date):

        inflows_node = self.node.inflows(
            date,
            next_date
        )

        maximum_inflows = self.maximum_inflows(
            date,
            next_date
        )

        turbined_inflows = min(
            inflows_node - self.instream_flow,
            maximum_inflows
        )

        return max(0, turbined_inflows)

    def maximum_corrected_power(self, date, next_date):
        """
        Compute the maximum power available after applying
        turbine availability constraints.

        Available generation capacity (MW).
        """

        # Retrieve turbine unavailability rate (between 0 and 1)
        unavailabilities = self.unavailabilities(date, next_date)

        # Compute corrected maximum power:
        # - If the turbine is fully available → full capacity (Pmax)
        # - If partially unavailable → reduce capacity proportionally
        # (1 - UN) represents the available fraction of the turbine
        corrected_maximum_power = min(
            self.maximum_power,
            (1 - unavailabilities) * self.maximum_power
        )

        return corrected_maximum_power

    def compute_power(self, date, next_date):
        """
        Compute the electrical power generated by the Hourat turbine.

        Electrical power output (MW).
        """

        turbined_inflows = self.turbined_inflows(
            date,
            next_date
        )

        efficiency = self.efficiency(
            date,
            next_date
        )

        maximum_corrected_power = self.maximum_corrected_power(
            date,
            next_date
        )

        power_hourat_turbine = min(
            turbined_inflows
            * efficiency
            * 3600,
            maximum_corrected_power
        )

        if power_hourat_turbine < self.minimum_power:
            power_hourat_turbine = 0

        power_artouste_turbine = (
            self.node.miegebat_node.artouste.power["valeur"].asof(date)
        )

        power_bious_turbine = (
            self.node.miegebat_node.bious.power["valeur"].asof(date)
        )

        power_fabreges_turbine = (
            self.node.miegebat_node.fabreges.power["valeur"].asof(date)
        )

        power_artouste_turbine = (
            0 if pd.isna(power_artouste_turbine)
            else power_artouste_turbine
        )

        power_bious_turbine = (
            0 if pd.isna(power_bious_turbine)
            else power_bious_turbine
        )

        power_fabreges_turbine = (
            0 if pd.isna(power_fabreges_turbine)
            else power_fabreges_turbine
        )

        # Jour 0 - Heure 1
        if date == self.start_date:

            special_condition = (
                    power_artouste_turbine <= 6
                    and (
                            power_bious_turbine
                            + power_fabreges_turbine
                    ) == 0
                    and (
                            (
                                    power_artouste_turbine
                                    + power_bious_turbine
                                    + power_fabreges_turbine
                            ) > 6
                            or (
                                    power_bious_turbine
                                    + power_fabreges_turbine
                            ) > 0
                    )
            )

        # Jour 0 - Heure 2 et suivantes
        else:

            previous_date = (
                    date - pd.Timedelta(hours=1)
            )

            previous_artouste_power = (
                self.node.miegebat_node.artouste.power["valeur"].asof(
                    previous_date
                )
            )

            previous_bious_power = (
                self.node.miegebat_node.bious.power["valeur"].asof(
                    previous_date
                )
            )

            previous_fabreges_power = (
                self.node.miegebat_node.fabreges.power["valeur"].asof(
                    previous_date
                )
            )

            previous_artouste_power = (
                0 if pd.isna(previous_artouste_power)
                else previous_artouste_power
            )

            previous_bious_power = (
                0 if pd.isna(previous_bious_power)
                else previous_bious_power
            )

            previous_fabreges_power = (
                0 if pd.isna(previous_fabreges_power)
                else previous_fabreges_power
            )

            special_condition = (
                    power_artouste_turbine <= 6
                    and (
                            power_bious_turbine
                            + power_fabreges_turbine
                    ) == 0
                    and (
                            (
                                    previous_artouste_power
                                    + previous_bious_power
                                    + previous_fabreges_power
                            ) > 6
                            or (
                                    previous_bious_power
                                    + previous_fabreges_power
                            ) > 0
                    )
            )

        if special_condition:
            power_hourat_turbine = max(
                3,
                power_hourat_turbine
            )

        return round(power_hourat_turbine, 1)

class GeteuTurbine(Turbine):

    def __init__(
        self,
        *args,
        hourat_turbine=None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.hourat_turbine = hourat_turbine

    def efficiency(self, date, next_date):

        reference_efficiency_hourat = (
            self.hourat_turbine.reference_efficiency(
                date,
                next_date
            )
        )

        return reference_efficiency_hourat / 5

    def unavailabilities(self, date, next_date):
        """
        Retrieve the turbine availability coefficient.

        Values are loaded from Hdx_data.
        """

        unavailabilities = (
            self.unavailability_df["valeur"].asof(date)
        )

        if pd.isna(unavailabilities):
            return 1

        return unavailabilities

    def maximum_inflows(self, date, next_date):

        return self.hourat_turbine.maximum_inflows(
            date,
            next_date
        )

    def turbined_inflows(self, date, next_date):

        inflows_hourat = self.hourat_turbine.turbined_inflows(
            date,
            next_date
        )

        maximum_inflows = self.maximum_inflows(
            date,
            next_date
        )

        return min(
            inflows_hourat,
            maximum_inflows
        )

    def maximum_corrected_power(self, date, next_date):

        unavailabilities = self.unavailabilities(
            date,
            next_date
        )

        corrected_maximum_power = min(
            self.maximum_power,
            (1 - unavailabilities) * self.maximum_power
        )

        return corrected_maximum_power

    def compute_power(self, date, next_date):

        turbined_inflows = self.turbined_inflows(
            date,
            next_date
        )

        efficiency = self.efficiency(
            date,
            next_date
        )

        maximum_corrected_power = self.maximum_corrected_power(
            date,
            next_date
        )

        power = max(
            min(
                turbined_inflows
                * efficiency
                * 3600,
                maximum_corrected_power
            ),
            0
        )

        return round(power, 1)

class CastetTurbine(Turbine):

    def __init__(
        self,
        *args,
        reference_maximum_inflows_from_pmax=None,
        hourat_turbine=None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.reference_maximum_inflows_from_pmax = (
            reference_maximum_inflows_from_pmax
        )

        self.hourat_turbine = hourat_turbine

    def efficiency(self, date, next_date):

        return 0.0000145

    def unavailabilities(self, date, next_date):
        """
        Retrieve the turbine availability coefficient.

        Values are loaded from Hdx_data.
        """

        unavailabilities = (
            self.unavailability_df["valeur"].asof(date)
        )

        if pd.isna(unavailabilities):
            return 1

        return unavailabilities

    def inflows(self, date, next_date):

        if self.optimal_outflow(date, next_date):
            return self.coefficient_castet(
                date,
                next_date
            )

        return self.sliding_outflow(
            date,
            next_date
        )

    def maximum_inflows(self, date, next_date):

        reference_maximum_inflows = (
            self.reference_maximum_inflows_from_pmax
        )

        maximum_corrected_power = (
            self.maximum_corrected_power(
                date,
                next_date
            )
        )

        efficiency = self.efficiency(
            date,
            next_date
        )

        if efficiency <= 1e-8:
            return 0

        maximum_inflows_from_power = (
                maximum_corrected_power
                /
                (efficiency * 3600)
        )

        return min(
            reference_maximum_inflows,
            maximum_inflows_from_power
        )

    def turbined_inflows(self, date, next_date):

        inflows = self.inflows(
            date,
            next_date
        )

        maximum_inflows = self.maximum_inflows(
            date,
            next_date
        )

        turbined_inflows = min(
            inflows - self.instream_flow,
            maximum_inflows
        )

        return max(0, turbined_inflows)

    def maximum_corrected_power(self, date, next_date):

        unavailabilities = self.unavailabilities(
            date,
            next_date
        )

        corrected_maximum_power = min(
            self.maximum_power,
            (1 - unavailabilities) * self.maximum_power
        )

        return corrected_maximum_power

    def sliding_outflow(self, date, next_date):

        day_start = date.normalize()

        hourat_flows = []
        castet_natural_inflows = []

        for hour in range(24):

            current_date = day_start + pd.Timedelta(hours=hour)

            hourat_flows.append(
                self.hourat_turbine.turbined_inflows(
                    current_date,
                    current_date + pd.Timedelta(hours=1)
                )
            )

            natural_inflow = (
                self.natural_inflows_df["valeur"].asof(
                    current_date
                )
            )

            if pd.notna(natural_inflow):
                castet_natural_inflows.append(
                    natural_inflow
                )

        return (
                np.mean(hourat_flows)
                +
                np.mean(castet_natural_inflows)
        )

    def optimal_outflow(self, date, next_date):
        """
        Compute the seasonal outflow indicator.

        Excel:
        Opt.Outflow =
        IF(
            AND(MONTH(cDate)>=7, MONTH(cDate)<=9),
            1,
            0
        )
        """

        if 7 <= date.month <= 9:
            return 1

        return 0

    def coefficient_castet(self, date, next_date):

        month = date.month

        if month == 8:
            return 4.5

        if month in (7, 9):
            return 5.5

        return 6

    def compute_power(self, date, next_date):

        turbined_inflows = self.turbined_inflows(
            date,
            next_date
        )

        efficiency = self.efficiency(
            date,
            next_date
        )

        maximum_corrected_power = self.maximum_corrected_power(
            date,
            next_date
        )

        power = min(
            turbined_inflows * efficiency * 3600,
            maximum_corrected_power
        )

        return round(power, 1)

class ArtousteTurbine(Turbine):

    def __init__(self, *args, **kwargs):
        """
        Initialize the Artouste turbine model.

        Efficiency reference values are stored to reproduce the
        time-freezing logic inherited from the original Excel model.
        """
        super().__init__(*args, **kwargs)

        self.eff_j0_h1 = None
        self.eff_j1_h1 = None

    def efficiency(self, date, next_date):
        """
        Compute the hydraulic efficiency coefficient K of the Artouste turbine.

        The hydraulic coefficient depends on the reservoir storage level,
        which acts as a proxy for the available hydraulic head.

        Two operating regimes are considered:

        - Above a reservoir threshold, the hydraulic head is assumed to
          remain sufficiently stable and a constant efficiency coefficient
          is used.

        - Below this threshold, the coefficient is calculated using an
          empirical relationship between reservoir storage and turbine
          performance.

        To reproduce the behaviour of the reference Excel model, the
        efficiency is frozen after the first hour of each simulation day.

        Hydraulic conversion coefficient K (MW/(m³/s)).
        """

        # Reservoir storage used as an indicator of hydraulic head.
        reference_level = self.reservoir.reference_level(date, next_date)  # (m)

        # Reservoir storage threshold separating the constant-head
        # and variable-head operating regimes.
        artouste_reservoir_water_level_1978 = 18000  # (Mm3)

        # Reference efficiency coefficient for high reservoir levels.
        artouste_K_water_level_1978 = 0.00171 * 0.96  # (MW/(m3/s))

        # High-storage regime: assume a constant hydraulic efficiency.
        if reference_level > artouste_reservoir_water_level_1978:
            # Return a constant K value.
            # In this regime, the system is assumed to operate under stable hydraulic conditions
            # (high reservoir level → nearly constant head → stable efficiency).
            efficiency = artouste_K_water_level_1978

        # Low-storage regime: estimate efficiency using the
        # empirical storage-efficiency relationship.
        else:
            # For lower reservoir levels, K is not constant and depends on the storage.
            # This empirical linear formula approximates the relationship observed in data
            # between reservoir volume and hydraulic performance.
            # As the reservoir level decreases:
            # - the hydraulic head decreases
            # - the efficiency of energy conversion slightly drops
            # → therefore K decreases
            # This formula is a linear interpolation fitted from historical/engineering data.

            efficiency = (
                                 0.00673 * reference_level / 1000
                                 + 1.51897
                         ) / 1000

        start_date = self.power.index[0]

        jour0_h1 = start_date + pd.Timedelta(hours=1)
        jour0_h2 = start_date + pd.Timedelta(hours=2)

        jour1_h1 = start_date + pd.Timedelta(days=1, hours=1)
        jour1_h2 = start_date + pd.Timedelta(days=1, hours=2)

        # Store the daily reference efficiencies
        if date == jour0_h1:
            self.eff_j0_h1 = efficiency
        if date == jour1_h1:
            self.eff_j1_h1 = efficiency

        # Freeze the efficiency for the remainder of Day 0.
        if (
                self.eff_j0_h1 is not None
                and jour0_h2 <= date < jour1_h1
        ):
            return self.eff_j0_h1

        # Freeze the efficiency for the remainder of Day 1.
        if (
                self.eff_j1_h1 is not None
                and date >= jour1_h2
        ):
            return self.eff_j1_h1

        return efficiency

    def inflows(self, date, next_date):
        """
        Convert electrical production into an equivalent hydraulic flow.

        Water flow is derived from power generation using the turbine
        efficiency coefficient.

        A dedicated low-load formulation is applied below 5 MW in order
        to avoid numerical instability and reproduce the historical
        operational behaviour of the plant.

        Turbined flow (m³/s).
        """

        # Retrieve the hydraulic conversion coefficient.
        efficiency = self.efficiency(date, next_date)

        # Retrieve the turbine production at the current timestep.
        # "asof" returns the last available value at or before the given date
        power = self.power["valeur"].asof(date)

        # Normal operating regimr (power > 5 MW)
        if power > 5:
            return power / (efficiency * 3600)

        # Low-load operating regime using a fixed coefficient (0 < power ≤ 5 MW)
        elif power > 0:
            # Use a fixed coefficient instead of variable efficiency
            # → avoids instability at low operating conditions
            return power / (0.0015936 * 3600)

        # No production → no flow
        return 0

    def maximum_volume(self, date, next_date):
        """
        Compute the maximum storage capacity of the Artouste reservoir.

        The calculation is based on the reservoir elevation-volume curve.
        The maximum authorized water level is converted into its
        corresponding storage volume using linear interpolation.

        Maximum reservoir storage (Mm³).
        """

        # Reservoir elevation-storage relationship.

        z_values = np.array([
            1919.00, 1920.00, 1921.00, 1922.00, 1923.00, 1924.00,
            1925.00, 1926.00, 1927.00, 1928.00, 1929.00, 1930.00,
            1931.00, 1932.00, 1933.00, 1934.00, 1935.00, 1936.00,
            1937.00, 1938.00, 1939.00, 1940.00, 1941.00, 1942.00,
            1943.00, 1944.00, 1945.00, 1946.00, 1947.00, 1948.00,
            1949.00, 1950.00, 1951.00, 1952.00, 1953.00, 1954.00,
            1955.00, 1956.00, 1957.00, 1958.00, 1959.00, 1960.00,
            1961.00, 1962.00, 1963.00, 1964.00, 1965.00, 1966.00,
            1967.00, 1968.00, 1969.00, 1970.00, 1971.00, 1972.00,
            1973.00, 1974.00, 1975.00, 1976.00, 1977.00, 1978.00,
            1979.00, 1980.00, 1981.00, 1982.00, 1983.00, 1984.00,
            1985.00, 1986.00, 1987.00, 1988.00, 1989.00, 1990.00,
            1990.20, 1990.93
        ])

        v_values = np.array([
            -157.50, 0.00, 157.00, 314.00, 472.00, 629.00,
            786.00, 970.00, 1153.00, 1336.00, 1520.00, 1703.00,
            1910.00, 2118.00, 2325.00, 2538.00, 2740.00, 2973.00,
            3207.00, 3440.00, 3673.00, 3907.00, 4165.00, 4423.00,
            4681.00, 4939.00, 5197.00, 5482.00, 5767.00, 6052.00,
            6336.00, 6621.00, 6938.00, 7255.00, 7571.00, 7888.00,
            8205.00, 8553.00, 8901.00, 9250.00, 9598.00, 9946.00,
            10329.00, 10712.00, 11095.00, 11478.00, 11861.00, 12284.00,
            12707.00, 13130.00, 13553.00, 13976.00, 14434.00, 14893.00,
            15352.00, 15811.00, 16270.00, 16763.00, 17256.00, 17749.00,
            18242.00, 18735.00, 19260.00, 19785.00, 20310.00, 20835.00,
            21359.00, 21894.00, 22430.00, 22965.00, 23500.00, 24042.00,
            24200.00, 24614.00
        ])

        # Slightly reduce the target elevation to avoid boundary effects
        # during interpolation.
        z_target = self.reservoir.maximum_level - 0.001


        # Convert the maximum reservoir elevation into its equivalent
        # storage volume using the elevation-storage relationship.
        self.maximum_volume_value = np.interp(z_target, z_values, v_values)

        # Maximum reservoir storage (Mm³).
        return self.maximum_volume_value

class BiousTurbine(Turbine):

    def __init__(self, *args, **kwargs):
        """
        Initialize the Bious turbine model.

        Internal state variables are used to cache previously computed
        efficiency values and reproduce the temporal behaviour of the
        reference Excel implementation.
        """

        super().__init__(*args, **kwargs)

        self.previous_efficiency = None
        self.efficiency_memory = {}
        self.eff_j2_h1 = None

    def efficiency(self, date, next_date):
        """
        Compute the hydraulic efficiency coefficient K of the Bious turbine.

        The efficiency is estimated using an empirical relationship based on
        both turbine power output and reservoir storage. Reservoir storage is
        used as a proxy for the available hydraulic head.

        To reproduce the behaviour of the reference operational model, the
        efficiency calculated on Day 2 Hour 1 is stored and reused for all
        subsequent timesteps.

        Hydraulic conversion coefficient K (MW/(m³/s)).
        """

        # Retrieve the turbine production at the current and next timestep.
        power = self.power["valeur"].asof(date)
        next_power = self.power["valeur"].asof(next_date)

        start_date = self.power.index[0]

        jour2_h1 = start_date + pd.Timedelta(days=2, hours=1)
        jour2_h2 = start_date + pd.Timedelta(days=2, hours=2)

        # Reuse the Day-2 reference efficiency for the remainder
        # of the simulation horizon.
        if (
                self.eff_j2_h1 is not None
                and date >= jour2_h2
        ):
            return self.eff_j2_h1

        # Return a previously computed value whenever available.
        if date in self.efficiency_memory:
            return self.efficiency_memory[date]

        # No production implies no effective hydraulic efficiency.
        if pd.isna(power) or power <= 0:
            return 0

        # Reservoir storage indicators used to estimate hydraulic head.
        level = self.reservoir.level(date, next_date)  # (Mm3) volume at hour h and hour h+1
        reference_level = self.reservoir.reference_level(date, next_date)  # (Mm3) reference volume at hour h

        def efficiency_bious_power_volume(power, volume):
            """
            Estimate the hydraulic efficiency coefficient from turbine
            power and reservoir storage.
            """

            # Convert storage to the units expected by the empirical model.
            v = volume / 1000

            # Empirical performance model calibrated from plant operating data.
            return power / (
                    3600 * (
                    (-0.00129048904 * v + 0.0220725572) * power ** 2
                    + (0.0096209161 * v + 0.0447369364) * power
                    + (-0.047219523 * v + 1.98986124))
            )

        # Invalid or zero power → no efficiency
        if pd.isna(power) or power <= 0:
            return 0

        # Apply minimum operating threshold:
        # Below 2 MW, use a fixed equivalent power (13.9 MW)
        # → avoids unstable or unrealistic efficiency values at low load
        power = 13.9 if power < 2 else power


        # Initial efficiency calculation.
        if self.previous_efficiency is None:
            # Use the reference storage level during initialization.
            efficiency = efficiency_bious_power_volume(
                power,
                reference_level
            )

        # Preserve the previous efficiency when operating conditions
        # remain unchanged.
        elif power == next_power:
            efficiency = self.previous_efficiency

        # If power changes → recompute using updated reservoir level
        else:
            # Use the simulated reservoir storage for the current interval.
            efficiency = efficiency_bious_power_volume(
                power,
                level
            )

        # Store the efficiency reference used from Day 2 onward.
        if date == jour2_h1:
            self.eff_j2_h1 = efficiency

        ## Preserve the computed efficiency for subsequent evaluations.
        self.previous_efficiency = efficiency
        self.efficiency_memory[date] = efficiency

        return efficiency  # (MW/(m3/s))

    def inflows(self, date, next_date):
        """
        Convert electrical production into an equivalent turbined flow.

        Water flow is derived from turbine power and the hydraulic
        efficiency coefficient.

        Turbined flow (m³/s).
        """

        # Retrieve turbine power (MW) at the given date
        # "asof" returns the latest available value at or before the timestamp
        power = self.power["valeur"].asof(date)

        # No production implies no turbined flow.
        if power <= 0:
            return 0

        # Retrieve the hydraulic conversion coefficient.
        efficiency = self.efficiency(date, next_date)

        # Avoid numerical instability (division by very small values)
        # WARNING : added to the original OURS formula
        if efficiency <= 1e-5:
            return 0

        # Convert power into water flow (m3/s equivalent)
        # The factor 3600 converts seconds to hours (1 hour = 3600 s),
        # ensuring consistency between power (MW, expressed per second)
        # and the model, which operates on hourly timesteps
        return power / (efficiency * 3600)

class FabregesTurbine(Turbine):

    def __init__(self, *args, **kwargs):
        """
        Initialize the Fabreges turbine model.

        Internal state variables are used to cache efficiency values and
        reproduce the temporal behaviour of the reference Excel model.
        """

        super().__init__(*args, **kwargs)

        self.previous_efficiency = None
        self.efficiency_memory = {}
        self.eff_j2_h1 = None

    def efficiency(self, date, next_date):
        """
        Compute the hydraulic efficiency coefficient K of the Fabreges turbine.

        The efficiency is derived from an empirical nonlinear relationship
        linking turbine power and reservoir storage. Reservoir storage is
        used as a proxy for hydraulic head and therefore influences the
        energy conversion performance of the plant.

        To reproduce the behaviour of the reference operational model,
        the efficiency calculated on Day 2 Hour 1 is stored and reused
        for all subsequent timesteps.

        Hydraulic conversion coefficient K (MW/(m³/s)).
        """

        # Retrieve the turbine production at the current and next timestep.
        power = self.power["valeur"].asof(date)
        next_power = self.power["valeur"].asof(next_date)

        start_date = self.power.index[0]

        jour2_h1 = start_date + pd.Timedelta(days=2, hours=1)
        jour2_h2 = start_date + pd.Timedelta(days=2, hours=2)

        # Reuse the Day-2 reference efficiency for the remainder
        # of the simulation horizon.
        if (
                self.eff_j2_h1 is not None
                and date >= jour2_h2
        ):
            return self.eff_j2_h1

        # Return a previously computed value whenever available.
        if date in self.efficiency_memory:
            return self.efficiency_memory[date]

        # No production implies no effective hydraulic efficiency.
        if pd.isna(power) or power <= 0:
            return 0

        # Retrieve the reservoir storage indicators used to estimate hydraulic head
        reference_level = self.reservoir.reference_level(date, next_date)  # (m3) reference volume at hour h

        level = self.reservoir.level(date, next_date)  # (m3) volume at hour h

        date_switch = self.power.index[0] + pd.Timedelta(days=2)

        # The reference storage is used from Day 2 onward to
        # reproduce the behaviour of the original model.
        if date >= date_switch:
            volume_for_efficiency = reference_level
        else:
            volume_for_efficiency = level

        def efficiency_fabreges_power_volume(power, volume):
            """
            Estimate the hydraulic efficiency coefficient from turbine
            power and reservoir storage.
            """

            # Convert storage to the units expected by the empirical model.
            v = volume / 1000

            # Empirical performance model calibrated from plant operating data.
            return power / (
                    3600 * (
                    (0.000683901465 * v ** 2 - 0.00855987384 * v + 0.0752195812) * power ** 2
                    + (0.00534712114 * v ** 2 - 0.066828544 * v + 0.689540814) * power
                    + (-0.000558325244 * v + 2.22661035)
            )
            )

        # No production implies no effective hydraulic efficiency.
        if pd.isna(power) or power <= 0:
            return 0

        # Apply the minimum operating point assumed by the efficiency model.
        power = 6.6 if power < 0.5 else power

        # Initial efficiency calculation.
        if self.previous_efficiency is None:
            next_power_adj = 6.6 if next_power < 0.5 else next_power
            efficiency = efficiency_fabreges_power_volume(
                next_power_adj,
                volume_for_efficiency
            )


        elif power == next_power:
            efficiency = self.previous_efficiency

        else:
            # Apply the same minimum-load assumption to the comparison timestep.
            next_power_adj = 6.6 if next_power < 0.5 else next_power
            efficiency = efficiency_fabreges_power_volume(
                next_power_adj,
                volume_for_efficiency
            )

        # Store the efficiency reference used from Day 2 onward.
        if date == jour2_h1:
            self.eff_j2_h1 = efficiency

        # Preserve the computed efficiency for subsequent evaluations.
        self.previous_efficiency = efficiency
        self.efficiency_memory[date] = efficiency

        return efficiency

    def inflows(self, date, next_date):
        """
        Convert electrical production into an equivalent turbined flow.

        Water flow is derived from turbine power and the hydraulic
        efficiency coefficient K.

        Turbined flow (m³/s).
        """

        # Retrieve the turbine production at the current timestep.
        power = self.power["valeur"].asof(date)

        # No production implies no turbined flow.
        if power <= 0:
            return 0

        # Hydraulic conversion coefficient derived from the plant
        # performance model.
        efficiency = self.efficiency(date, next_date)

        # Numerical safeguard against unrealistic flow values.
        if efficiency <= 1e-5:
            return 0

        # Convert power (MW) into water flow (m3/s equivalent)
        # The factor 3600 converts from seconds to hours (1 hour = 3600 s)
        # ensuring consistency with the model's hourly timestep

        return power / (efficiency * 3600)

class PontDeCampsTurbine(Turbine):

    def __init__(self, *args, **kwargs):
        """
        Initialize the Pont de Camps turbine model.

        Efficiency reference values are stored to reproduce the
        time-freezing logic inherited from the reference Excel model.
        """
        super().__init__(*args, **kwargs)

        self.eff_j0_h1 = None
        self.eff_j1_h1 = None

    def efficiency(self, date, next_date):
        """
        Compute the hydraulic efficiency coefficient K of the Pont de Camps turbine.

        The efficiency coefficient is estimated using an empirical relationship
        based on reservoir storage. Reservoir storage acts as a proxy for the
        available hydraulic head and therefore influences turbine performance.

        To reproduce the behaviour of the reference Excel model, the efficiency
        is frozen after specific reference hours and reused for the remainder
        of the corresponding simulation period.

        Hydraulic conversion coefficient K (MW/(m³/s)).
        """

        # Retrieve the reservoir storage used as a proxy for hydraulic head.
        reference_level = self.reservoir.reference_level(date, next_date)  # (m3) reference volume at hour h

        # Empirical relationship between reservoir storage and
        # hydraulic conversion efficiency.
        efficiency = (
                (
                        -0.00022 * (reference_level / 1000) ** 2
                        + 0.01089 * (reference_level / 1000)
                        + 1.52447
                ) / 1000
        )

        start_date = self.power.index[0]

        jour0_h1 = start_date + pd.Timedelta(hours=1)
        jour0_h2 = start_date + pd.Timedelta(hours=2)

        jour1_h1 = start_date + pd.Timedelta(days=1, hours=1)
        jour1_h2 = start_date + pd.Timedelta(days=1, hours=2)

        # Store the daily efficiency reference values.
        if date == jour0_h1:
            self.eff_j0_h1 = efficiency
        if date == jour1_h1:
            self.eff_j1_h1 = efficiency

        # Freeze the efficiency for the remainder of Day 0.
        if (
                self.eff_j0_h1 is not None
                and jour0_h2 <= date < jour1_h1
        ):
            return self.eff_j0_h1

        # Freeze the efficiency from the second hour of Day 1 onward.
        if (
                self.eff_j1_h1 is not None
                and date >= jour1_h2
        ):
            return self.eff_j1_h1

        return efficiency # (MW/(m³/s))

    def inflows(self, date, next_date):
        """
        Convert electrical production into an equivalent turbined flow.

        Water flow is derived from turbine power and the hydraulic
        efficiency coefficient K.

        Turbined flow (m³/s).
        """

        # Retrieve the hydraulic conversion coefficient.
        efficiency = self.efficiency(date, next_date)

        # Retrieve the turbine production at the current timestep.
        power = self.power["valeur"].asof(date)

        # No production implies no turbined flow.
        if pd.isna(power) or power <= 0:
            return 0

        # Numerical safeguard against unrealistic flow values.
        if efficiency <= 1e-5:
            return 0

        # Convert electrical power into its hydraulic equivalent.
        return power / (efficiency * 3600) # (m3/s)

    def turbined_inflows(self, date, next_date):
        """
        Compute the effective flow passing through the turbine.

        Turbined flow (m³/s).
        """

        # Retrieve turbine production at the current timestep.
        # "asof" returns the latest available value at or before the timestamp
        power = self.power["valeur"].asof(date)

        # Compute the hydraulic conversion coefficient.
        efficiency= self.efficiency(date, next_date)

        # If the turbine is operating → convert power into water flow
        if power > 0:
            inflows = power / (efficiency * 3600)

        else:
            # No production → no water is turbinated
            inflows= 0

        return inflows

@dataclass
class Reservoir:
    """
    Abstract base class representing a hydraulic reservoir.

    A reservoir stores water and regulates its release through
    turbines, valves, or spillways. Reservoirs are central elements
    of the hydraulic system because they determine the available
    storage volume, influence the hydraulic head, and contribute
    to the overall water balance of the network.

    Each reservoir implementation is responsible for defining
    its own storage-elevation relationships, water balance equations,
    inflow calculations, and operational constraints.
    """

    # Unique identifier of the reservoir.
    name: str

    # Time series containing reservoir storage levels.
    level_df: pd.DataFrame | None = None

    # Time series containing natural water inflows entering
    # the reservoir (m³/s).
    natural_inflows_df: pd.DataFrame | None = None

    # Time series containing valve or spillway releases.
    inflows_vanne_df: pd.DataFrame | None = None

    # Minimum allowable storage volume.
    minimum_volume: float | None = None

    # Maximum authorized water elevation.
    maximum_level: float | None = None

    # Valve associated with the reservoir.
    valve: object | None = None

    # Turbine supplied by the reservoir.
    turbine: object | None = None

    def maximum_volume(self, date, next_date):
        """
        Compute the maximum storage capacity of the reservoir.

        Maximum reservoir storage volume.
        """
        raise NotImplementedError("Each reservoir must define its maximum volume")

    def level(self, date, next_date):
        """
        Compute the reservoir storage level.

        Reservoir storage volume at the current timestep.
        """
        raise NotImplementedError("Each reservoir must define its level")

    def reference_level(self, date, next_date):
        """
        Retrieve the reference reservoir level.

        The reference level is generally based on measured data
        and may be used as a fallback when simulated values are
        unavailable.

        Reference reservoir storage volume.
        """
        raise NotImplementedError("Each reservoir must define its reference level")

    def inflows(self, date, next_date):
        """
        Compute the net reservoir inflow.

        Net inflow typically includes natural inflows, upstream
        releases, turbine withdrawals, and valve discharges.

        Net inflow rate (m³/s).
        """
        raise NotImplementedError("Each reservoir must define its inflows")

class ArtousteReservoir(Reservoir):
    """
    Reservoir model associated with the Artouste hydroelectric scheme.

    The reservoir storage is primarily driven by measured data.
    When observations are unavailable, fallback values derived from
    the reservoir operating limits are used.

    The class also provides the elevation-storage relationship required
    to convert the maximum authorized water level into an equivalent
    storage volume.
    """

    #def __post_init__(self):

    def maximum_volume(self, date, next_date):
        """
        Compute the maximum storage capacity of the Artouste reservoir.

        The computation relies on the reservoir elevation-storage curve.
        The maximum authorized water elevation is converted into an
        equivalent storage volume using linear interpolation.

        Maximum reservoir storage (Mm³).
        """

        # Height–volume conversion table for the Artouste reservoir.

        # z_values represent water elevations (m).
        z_values = np.array([
            1919.00, 1920.00, 1921.00, 1922.00, 1923.00, 1924.00,
            1925.00, 1926.00, 1927.00, 1928.00, 1929.00, 1930.00,
            1931.00, 1932.00, 1933.00, 1934.00, 1935.00, 1936.00,
            1937.00, 1938.00, 1939.00, 1940.00, 1941.00, 1942.00,
            1943.00, 1944.00, 1945.00, 1946.00, 1947.00, 1948.00,
            1949.00, 1950.00, 1951.00, 1952.00, 1953.00, 1954.00,
            1955.00, 1956.00, 1957.00, 1958.00, 1959.00, 1960.00,
            1961.00, 1962.00, 1963.00, 1964.00, 1965.00, 1966.00,
            1967.00, 1968.00, 1969.00, 1970.00, 1971.00, 1972.00,
            1973.00, 1974.00, 1975.00, 1976.00, 1977.00, 1978.00,
            1979.00, 1980.00, 1981.00, 1982.00, 1983.00, 1984.00,
            1985.00, 1986.00, 1987.00, 1988.00, 1989.00, 1990.00,
            1990.20, 1990.93
        ])

        # v_values represent the corresponding reservoir storage volumes (Mm³).
        v_values = np.array([
            -157.50, 0.00, 157.00, 314.00, 472.00, 629.00,
            786.00, 970.00, 1153.00, 1336.00, 1520.00, 1703.00,
            1910.00, 2118.00, 2325.00, 2538.00, 2740.00, 2973.00,
            3207.00, 3440.00, 3673.00, 3907.00, 4165.00, 4423.00,
            4681.00, 4939.00, 5197.00, 5482.00, 5767.00, 6052.00,
            6336.00, 6621.00, 6938.00, 7255.00, 7571.00, 7888.00,
            8205.00, 8553.00, 8901.00, 9250.00, 9598.00, 9946.00,
            10329.00, 10712.00, 11095.00, 11478.00, 11861.00, 12284.00,
            12707.00, 13130.00, 13553.00, 13976.00, 14434.00, 14893.00,
            15352.00, 15811.00, 16270.00, 16763.00, 17256.00, 17749.00,
            18242.00, 18735.00, 19260.00, 19785.00, 20310.00, 20835.00,
            21359.00, 21894.00, 22430.00, 22965.00, 23500.00, 24042.00,
            24200.00, 24614.00
        ])

        # Target elevation slightly reduced to avoid edge effects during interpolation
        # (ensures interpolation remains within bounds of the dataset)
        z_target = self.maximum_level - 0.001

        # Linear interpolation to compute the corresponding maximum volume
        # based on the elevation–volume relationship
        self.maximum_volume_value = np.interp(z_target, z_values, v_values)  # (Mm³)

        # Return maximum reservoir storage
        return self.maximum_volume_value # (Mm³)

    def reference_level(self, date, next_date):

        # Ensure that the maximum reservoir volume is initialized.
        # This value is required as a fallback in case data is missing
        if not hasattr(self, "maximum_volume_value"):
            self.maximum_volume(date, next_date)

        # Retrieve the reservoir storage value at the given date.
        # Returns the last available value at or before the given timestamp.
        level = self.level_df["valeur"].asof(date)  # (103m3) volume at hour h

        # If a valid value is available, return it مباشرة
        if pd.notna(level):
            return level
        else:
            # If the value is missing (NaN), return a fallback estimate.
            # The fallback is defined as the average between:
            # - maximum reservoir volume
            # - minimum reservoir volume
            # This provides a neutral estimate of the reservoir storage
            # when no measurement data is available.
            return (self.maximum_volume_value + self.minimum_volume) / 2

class BiousReservoir(Reservoir):
    """
    Reservoir model associated with the Bious hydroelectric scheme.

    Reservoir storage is determined from measured data whenever
    available. When observations are missing, storage is estimated
    through a water balance equation combining natural inflows and
    turbine withdrawals.

    The class also provides the elevation-storage relationship
    required to determine the maximum reservoir capacity.
    """

    # def __post_init__(self):

    def maximum_volume(self, date, next_date):

        # Height–volume conversion table for the Bious reservoir.

        # z_values represent water elevations (in meters above sea level).
        z_values = np.array([
            1385.00, 1386.00, 1387.00, 1388.00, 1389.00, 1390.00,
            1391.00, 1392.00, 1393.00, 1394.00, 1395.00, 1396.00,
            1397.00, 1398.00, 1399.00, 1400.00, 1401.00, 1402.00,
            1403.00, 1404.00, 1405.00, 1406.00, 1407.00, 1408.00,
            1409.00, 1410.00, 1411.00, 1412.00, 1413.00, 1414.00,
            1415.00, 1416.00, 1417.00, 1418.00
        ])

        # v_values represent the corresponding reservoir storage volumes (Mm³).
        v_values = np.array([
            -216, -147, -62, 0, 49, 108,
            173, 263, 363, 463, 603, 743,
            893, 1043, 1203, 1373, 1543, 1723,
            1913, 2103, 2343, 2580, 2820, 3090,
            3360, 3630, 3900, 4180, 4470, 4760,
            5050, 5343, 5633, 5924.5
        ])

        # Target elevation slightly reduced to avoid extrapolation or boundary effects
        # during interpolation (numerical stability)
        z_target = self.maximum_level - 0.001

        # Linear interpolation to estimate the corresponding maximum reservoir volume (Mm³)
        # based on the height–volume relationship
        self.maximum_volume_value = np.interp(z_target, z_values, v_values)

        # Return the maximum storage capacity of the Bious reservoir
        return self.maximum_volume_value

    def level(self, date, next_date):
        """
        Compute the reservoir storage level.

        Measured storage values are used whenever available.
        Otherwise, storage is estimated through a reservoir balance
        equation based on natural inflows and turbine withdrawals.

        Computed values are cached to avoid recursive evaluations and
        ensure consistency across dependent calculations.

        Reservoir storage volume.
        """

        # Cache computed storage levels to avoid recursive evaluations.
        if not hasattr(self, "level_memory"):
            self.level_memory = {}

        # Reuse previously calculated values whenever available.
        if date in self.level_memory:
            return self.level_memory[date]

        # Initialize the maximum storage capacity if required.
        if not hasattr(self, "maximum_volume_value"):
            self.maximum_volume(date, next_date)

        maximum_volume = self.maximum_volume_value

        # Observed reservoir storage at the current timestep.
        value = self.level_df["valeur"].asof(date)

        # Use measured data whenever available.
        if pd.notna(value):
            level = value

        else:
            reference_level = self.reference_level(date, next_date)
            # Store a temporary value to prevent recursive dependencies.
            self.level_memory[date] = reference_level
            # Components required for the reservoir water balance.
            natural_inflows = self.natural_inflows_df["valeur"].asof(date)
            inflows = self.inflows(date, next_date)
            previous_date = date - pd.Timedelta(hours=1)

            if previous_date in self.level_memory:
                previous_level = self.level_memory[previous_date]

            else:
                previous_level = reference_level
            # Fall back to the reference storage level when the
            # water balance cannot be evaluated.

            if pd.isna(natural_inflows) or pd.isna(inflows):
                level = reference_level

            else:
                # Net reservoir inflow.
                net_inflows = natural_inflows - inflows
                # Reservoir balance equation.
                # The factor 3.6 converts flow rates into the storage units
                # used by the model.
                level = previous_level + net_inflows * 3.6

            # Enforce the physical storage limit of the reservoir.
            level = min(level, maximum_volume)

            # Cache the computed storage level.
            self.level_memory[date] = level

            return level

    def reference_level(self, date, next_date):

        # Ensure that the maximum reservoir volume is initialized.
        # This value is required as a fallback in case data is missing
        if not hasattr(self, "maximum_volume_value"):
            self.maximum_volume(date, next_date)

        # Retrieve the reservoir storage value at the given date.
        level = self.level_df["valeur"].asof(date)  # (103m3) volume at hour h

        # If a valid value is available, return it
        if pd.notna(level):
            return level
        else:
            # If the value is missing (NaN), return a fallback estimate.
            # The fallback is defined as the average between:
            # - maximum reservoir volume
            # - minimum reservoir volume
            # This provides a neutral estimate of the reservoir storage
            # when no measurement data is available.
            return (self.maximum_volume_value + self.minimum_volume) / 2

    def inflows(self, date, next_date):

        # compute the net reervoir flow (storage variation) at Bious:
        # retrieve natural inflows of Bious reservoir and inflows going to the Bious turbine (leaving the reservoir basically)
        natural_inflows = self.natural_inflows_df["valeur"].asof(date)
        inflows_turbine = self.turbine.inflows(date, next_date)
        # natural inflows entering the reservoir minus the turbine outflows (what comes in - what comes out)
        inflows = natural_inflows - inflows_turbine

        return inflows # (m3/s)

class FabregesReservoir(Reservoir):
    """
    Reservoir model associated with the Fabreges hydroelectric scheme.

    Reservoir storage is determined from measured observations whenever
    available. When data are missing, storage is estimated through a
    water balance equation combining natural inflows, upstream turbine
    releases, turbine withdrawals, and valve discharges.

    The reservoir also provides the elevation-storage relationship
    required to compute the maximum storage capacity.
    """

    # def __post_init__(self):

    def maximum_volume(self, date, next_date):
        """
        Compute the maximum storage capacity of the Fabreges reservoir.

        The maximum authorized water level is converted into an equivalent
        storage volume using the reservoir elevation-storage curve.

        Maximum reservoir storage (Mm³).
        """

        # Height–volume conversion table for the Fabreges reservoir.

        # z_values represent water elevations (m).
        z_values = np.array([
            1202.00, 1203.00, 1204.00, 1205.00, 1206.00, 1207.00,
            1208.00, 1209.00, 1210.00, 1211.00, 1212.00, 1213.00,
            1214.00, 1215.00, 1216.00, 1217.00, 1217.50, 1218.00,
            1219.00, 1220.00, 1221.00, 1222.00, 1223.00, 1224.00,
            1225.00, 1226.00, 1227.00, 1228.00, 1229.00, 1230.00,
            1231.00, 1232.00, 1232.50, 1233.00, 1233.50, 1234.00,
            1234.50, 1235.00, 1235.50, 1236.00, 1236.50, 1237.00,
            1237.50, 1238.00, 1238.50, 1239.00, 1239.50, 1240.00,
            1240.01, 1240.76, 1241.21
        ])

        # v_values represent the corresponding reservoir storage volumes (Mm³).
        v_values = np.array([
            -45.50, -30.50, -15.50, 0.00, 14.00, 29.00,
            45.00, 63.00, 83.00, 107.00, 135.00, 170.00,
            211.00, 264.00, 330.00, 410.00, 455.00, 500.00,
            620.00, 745.00, 865.00, 1015.00, 1180.00, 1370.00,
            1580.00, 1810.00, 2070.00, 2340.00, 2630.00, 2930.00,
            3250.00, 3580.00, 3755.00, 3930.00, 4110.00, 4290.00,
            4480.00, 4670.00, 4865.00, 5060.00, 5255.00, 5450.00,
            5650.00, 5850.00, 6060.00, 6270.00, 6485.00, 6700.00,
            6750.00, 7033.93, 7229.94
        ])

        # Target elevation slightly reduced to avoid edge effects during interpolation
        # (ensures interpolation remains within bounds of the dataset)
        z_target = self.maximum_level - 0.001

        # Linear interpolation to compute the corresponding maximum volume
        # based on the elevation–volume relationship
        self.maximum_volume_value = np.interp(z_target, z_values, v_values)

        # Return maximum reservoir storage
        return self.maximum_volume_value # (Mm³)


    def level(self, date, next_date):
        """
        Compute the reservoir storage level.

        Measured storage values are used whenever available.
        Otherwise, storage is estimated using a reservoir balance equation
        based on the net inflow entering the reservoir.

        Computed values are cached to avoid recursive evaluations and
        ensure consistency across dependent hydraulic calculations.

        Reservoir storage volume.
        """

        # Initialize memory storage
        # Used to avoid recalculating the same reservoir level multiple times
        if not hasattr(self, "level_memory"):
            self.level_memory = {}

        # If the level has already been requested
        if date in self.level_memory:

            stored_value = self.level_memory[date]

            # Return the previously computed level
            return stored_value

        # Retrieve maximum reservoir storage capacity
        maximum_volume = self.maximum_volume(date, next_date)

        # Reference reservoir level used as fallback
        reference_level = self.reference_level(date, next_date)

        # Check whether an observed level exists in the input data
        value = self.level_df["valeur"].asof(date)

        # Temporary value to break recursion
        self.level_memory[date] = (
            value if pd.notna(value) else reference_level
        )

        # Case 1: measured level available
        if pd.notna(value):

            level = value

        # Case 2: level must be estimated
        else:

            # Compute reservoir net inflow
            inflows = self.inflows(date, next_date)

            # Get previous timestep
            previous_date = date - pd.Timedelta(hours=1)

            level = reference_level + inflows * 3.6

        # Apply physical constraints
        level = max(0, min(level, maximum_volume))

        # Store the final computed level
        self.level_memory[date] = level

        return level

    def reference_level(self, date, next_date):

        # Ensure that the maximum reservoir volume is initialized.
        # This value is required as a fallback in case data is missing
        if not hasattr(self, "maximum_volume_value"):
            self.maximum_volume(date, next_date)

            # Retrieve the reservoir storage value at the given date.
        level = self.level_df["valeur"].asof(date) # (103m3) volume at hour h

        # If a valid value is available
        if pd.notna(level):
            return level

        else:
            # If the value is missing (NaN), return a fallback estimate.
            # The fallback is defined as the average between:
            # - maximum reservoir volume
            # - minimum reservoir volume
            # This provides a neutral estimate of the reservoir storage
            # when no measurement data is available.


            return (self.maximum_volume_value + self.minimum_volume) / 2

    def inflows(self, date, next_date):

        # Natural inflows entering the Fabreges reservoir (m3/s)
        # These represent external water inputs (rainfall, upstream rivers, etc.)
        natural_inflows = self.natural_inflows_df["valeur"].asof(date)

        # Inflow coming from upstream turbine (Pont de Camps)
        # This is water released upstream that reaches the Fabreges reservoir
        inflows_pont_de_camps = self.pont_de_camps_turbine.inflows(date, next_date)

        # Outflow through the Fabreges turbine (water used for power generation)
        inflows_fabreges = self.fabreges_turbine.inflows(date, next_date)

        # Outflow through Fabreges spillway/valve (non-turbined release)
        inflows_valve = self.valve.inflows(date, next_date)

        # Reservoir water balance:
        # inflows (natural + upstream turbine) minus outflows (turbine + valve)
        # → represents the net variation of stored water in the reservoir
        inflows = (
                natural_inflows
                + inflows_pont_de_camps
                - inflows_fabreges
                - inflows_valve
        )

        return inflows

@dataclass
class Valve:
    """
    Abstract base class representing a hydraulic valve or spillway.

    A valve controls water releases that bypass power generation
    facilities. These releases contribute to the hydraulic balance
    of the downstream system and must therefore be accounted for
    in reservoir and node inflow calculations.

    Each valve implementation is responsible for defining its own
    release calculation logic.
    """

    # Unique identifier of the valve.
    name: str

    # Time series containing valve releases or natural spillway inflows.
    natural_inflows: pd.DataFrame | None = None

    def inflows(self, date, next_date):
        """
        Compute the flow released through the valve.

        Valve discharge (m³/s).
        """
        raise NotImplementedError("Each valve must define its inflows")

class FabregesValve(Valve):
    """
    Valve model associated with the Fabreges reservoir.

    The valve discharge is directly obtained from the available
    time-series data and contributes to the downstream hydraulic
    balance of the system.
    """

    def inflows(self, date, next_date):
        """
        Retrieve the valve discharge at the current timestep.

        Valve release flow (m³/s).
        """

        # Valve discharge at the current timestep. (m3/s)
        natural_inflows = self.natural_inflows["valeur"].asof(date)

        if pd.notna(natural_inflows):
            return natural_inflows

        # Assume no release when no value is available.
        return 0

@dataclass
class Node:
    """
    Abstract base class representing a hydraulic network node.

    A node aggregates water contributions from multiple upstream
    hydraulic assets and redistributes them downstream.

    Nodes are used to represent hydraulic junctions where flows
    from turbines, reservoirs, spillways, and natural inflows
    converge.

    Each node implementation must define its own inflow
    aggregation logic.
    """

    # Unique identifier of the node.
    name: str

    # Node category used within the hydraulic model.
    type: str = None

    def inflows(self, date, next_date):
        """
        Compute the total inflow entering the node.

        Aggregated node inflow (m³/s).
        """
        raise NotImplementedError(
            "Each node must define its inflows"
        )

class MiegebatNode(Node):
    """
    Hydraulic aggregation node located upstream of the
    Miegebat turbine.

    The node combines water contributions from upstream
    hydroelectric facilities, valve releases, and natural
    inflows before routing the resulting flow toward the
    Miegebat power plant.
    """

    def inflows(self, date, next_date):
        """
        Compute the total inflow arriving at the Miegebat node.

        The node aggregates:
        - turbine releases from Artouste,
        - turbine releases from Bious,
        - turbine releases from Fabreges,
        - Fabreges valve releases,
        - natural inflows from the Allias catchment.

        Total inflow at the Miegebat node (m³/s).
        """

        # Compute upstream turbine flows (m3/s equivalent) contributing to the Miegebat node
        # These flows are already calculated using each turbine's specific conversion:
        inflows_artouste_turbine = self.artouste.inflows(date, next_date)
        inflows_bious_turbine = self.bious.inflows(date, next_date)
        inflows_fabreges_turbine = self.fabreges.inflows(date, next_date)

        # Additional contribution from Fabreges spillway (valve flow)
        inflows_fabreges_valve = (
            self.fabreges.reservoir.valve.inflows(date, next_date)
        )

        # Natural inflows entering the system at the Allias node (m3/s)
        # This represents exogenous water input (not coming from turbines)
        natural_inflows_allias_reservoir = self.natural_inflows_allias_df["valeur"].asof(date)

        # Compute total inflow at the Miegebat node:
        # This node aggregates all upstream contributions in the hydraulic network:
        # - turbine releases (Artouste, Bious, Fabreges)
        # - valve releases (Fabreges)
        # - natural inflows (Allias reservoir)
        # The max(..., 0) ensures physical consistency (no negative flow)
        inflows_miegebat_node = max(
            inflows_fabreges_turbine
            + inflows_bious_turbine
            + inflows_artouste_turbine
            + inflows_fabreges_valve
            + natural_inflows_allias_reservoir,
            0
        )

        # Return total inflow at Miegebat node
        return inflows_miegebat_node

class HouratNode(Node):
    """
    Hydraulic aggregation node located upstream of the
    Hourat turbine.

    The node combines water contributions from the
    Miegebat node and the natural inflows entering
    the Hourat catchment.
    """

    def inflows(self, date, next_date):

        # Inflows coming from the upstream Miegebat node
        inflows_miegebat_node = self.miegebat_node.inflows(
            date,
            next_date
        )

        # Natural inflows entering the Hourat catchment
        natural_inflows_hourat_reservoir = (
            self.natural_inflows_hourat_df["valeur"].asof(date)
        )

        # Compute total inflow at Hourat node
        inflows_hourat_node = max(
            inflows_miegebat_node
            + natural_inflows_hourat_reservoir,
            0
        )

        # Return total inflow at Hourat node
        return inflows_hourat_node



