import os
import pathlib
from typing import Mapping
import math
import decimal

import tomli
import tqdm

import thtools as tt

HOME = os.path.dirname(os.path.abspath(__file__))

EXTRA_SIZE = 1
N_SAMPLES = 100
CELSIUS_RANGE = range(0, 100, 10)
Z_SCORE = 1.96
TEXT = """===Information contributed by City of London UK (2021)===
[[File:ToeholdTools.png|x200px|center]]

This toehold switch was characterized <i>in silico</i> using the ToeholdTools project that our team developed.
See https://github.com/lkn849/thtools for more information.
 
Metadata:
*'''Group:''' City of London UK 2021
*'''Author:''' Lucas Ng
*'''Summary:''' Used our software ToeholdTools to investigate the target miRNA specificity and activation of this part.
 
Raw data:
*[[Media:{part}_thtest.txt]]
*[[Media:{part}_thtest.csv]]
*[[Media:{part}_crt.txt]]
*[[Media:{part}_crt.csv]]

This contribution was autogenerated by the script https://github.com/lkn849/thtools/registry/contrib.py using the configuration file https://github.com/lkn849/thtools/registry/{team}.toml.

----

This switch was designed to detect the miRNA {target} at a temperature of {celsius}.
We tested it against every <i>{species}</i> RNA in miRBase and our analysis shows that it is best used to detect {inferred_target_name}.

With {inferred_target_name} at {celsius}°C, the switch has a specificity of {specificity} ± {specificity_se} % and an activation of {activation} ± {activation_se} %.
These values represent 95% confidence limits (z=1.96).

The temperature&ndash;activation&ndash;specificity relationship is shown here:

[[File:{part}_crt.png|500px|center]]

Error bars represent the standard error (SE).
The line of best fit was calculated using a univariate B-spline weighted inverse to each point's SE.

"""
BAD_SWITCH = """'''Since this switch does not accurately detect the desired target miRNA, we do not recommend this part for use.'''"""


def mkdir(path):
    try:
        os.mkdir(path)
    except FileExistsError:
        pass


def to_one_sf(x: float) -> decimal.Decimal:
    if x != float("inf"):
        raw = round(x, -int(math.floor(math.log10(abs(x)))))
        if raw >= 1:
            raw = int(raw)
    else:
        raw = x
    return decimal.Decimal(str(raw))


def to_dp(x: float, dp) -> decimal.Decimal:
    x = decimal.Decimal(str(x))
    try:
        return x.quantize(decimal.Decimal(str(10 ** -dp)))
    except decimal.InvalidOperation:
        return x


def dp_count(x: decimal.Decimal) -> int:
    val = x.as_tuple().exponent
    return abs(val) if not isinstance(val, str) else 0


def to_same_dp(x, template):
    return to_dp(x, dp_count(template)) if template != float("inf") else int(x)


class Contribution:
    toml_dict: dict

    team: str
    rbs: str
    species: str
    celsius: str

    fasta: tt.FParser
    mirna: dict
    test: tt.ToeholdTest

    thtests: Mapping[str, Mapping[str, tt.ToeholdResult]]
    crts: Mapping[str, Mapping[str, tt.CelsiusRangeResult]]

    def __init__(self, path: str, autorun=True):
        self.team = pathlib.Path(path).stem
        with open(path, "rb") as f:
            self.toml_dict = tomli.load(f)
        self.rbs = self.toml_dict["rbs"]
        self.species = self.toml_dict["species"]
        self.celsius = self.toml_dict["celsius"]
        self.fasta = tt.FParser.fromspecies(self.species)  # [29:75]  # [48:53]
        self.mirna = {
            key: value
            for key, value in self.toml_dict.items()
            if key not in ("rbs", "species", "celsius")
        }
        self.thtests = {}
        self.crts = {}
        if autorun:
            self.run()
            self.save()

    def run(self):
        for mirna, switch in tqdm.tqdm(self.mirna.items(), desc=self.team):
            toeholds = tt.FParser.fromregistry(parts=switch["toeholds"])
            if "antis" in switch:
                antis = [
                    [tt.FParser.fromregistry(part=part).seqs[0].upper()]
                    if part
                    else None
                    for part in switch["antis"]
                ]
            else:
                antis = [None] * len(toeholds)
            self.thtests[mirna] = {}
            self.crts[mirna] = {}
            for ths, name, anti in tqdm.tqdm(
                zip(toeholds.seqs, toeholds.ids, antis),
                total=len(toeholds),
                desc=mirna,
                leave=None,
            ):
                thtest = tt.autoconfig(
                    ths.replace("T", "U").replace("t", "U"),
                    self.rbs,
                    self.fasta.seqs,
                    names=self.fasta.ids,
                    const_rna=anti,
                )
                with tqdm.tqdm(
                    total=len(CELSIUS_RANGE) + 1, desc=name, leave=None
                ) as switch_bar:
                    self.thtests[mirna][name] = thtest.run(
                        max_size=len(toeholds) + len(antis) + 1
                    )
                    switch_bar.update()
                    crt = tt.CelsiusRangeTest(thtest, CELSIUS_RANGE)
                    for _ in crt.generate(max_size=len(toeholds) + len(antis) + 1):
                        switch_bar.update()
                    self.crts[mirna][name] = crt.result
        print(f"Simulation of team {self.team}'s toehold switches finished")

    def save(self):
        mkdir(os.path.join(HOME, "contributions"))
        mkdir(os.path.join(HOME, "contributions", self.team))
        for (mirna, thtests), (mirna, crts) in zip(
            self.thtests.items(), self.crts.items()
        ):
            for (name, thtest), (name, crt) in zip(thtests.items(), crts.items()):
                crt.inferred_target_name = thtest.target_name
                partdir = os.path.join(HOME, "contributions", self.team, name)
                mkdir(partdir)
                with open(
                    os.path.join(partdir, name + "_thtest.txt"),
                    "w",
                ) as f:
                    f.write(thtest.prettify())
                with open(
                    os.path.join(partdir, name + "_thtest.csv"),
                    "w",
                ) as f:
                    f.write(thtest.to_csv())
                with open(
                    os.path.join(partdir, name + "_crt.txt"),
                    "w",
                ) as f:
                    f.write(crt.prettify())
                with open(
                    os.path.join(partdir, name + "_crt.csv"),
                    "w",
                ) as f:
                    f.write(crt.to_csv())
                crt.savefig(os.path.join(partdir, name + "_graph.png"), z_score=1)
                specificity_se = to_one_sf(thtest.specificity_se * Z_SCORE * 100)
                specificity = to_same_dp(thtest.specificity * 100, specificity_se)
                activation_se = to_one_sf(thtest.target_activation_se * Z_SCORE * 100)
                activation = to_same_dp(
                    thtest.target_activation * Z_SCORE * 100, activation_se
                )
                desc = TEXT.format(
                    part=name,
                    target=mirna,
                    inferred_target_name=thtest.target_name,
                    celsius=self.celsius,
                    specificity=specificity,
                    specificity_se=specificity_se,
                    activation=activation,
                    activation_se=activation_se,
                    team=self.team,
                    species=self.species,
                )
                if mirna != thtest.target_name:
                    desc += BAD_SWITCH
                with open(os.path.join(partdir, "desc"), "w") as f:
                    f.write(desc)
        print(f"Results for {self.team} saved.")


if __name__ == "__main__":
    Contribution(os.path.join(HOME, "2019_SASTRA_Thanjavur.toml"))
    Contribution(os.path.join(HOME, "2017_CLSB_UK.toml"))
    Contribution(os.path.join(HOME, "2020_CSMU_Taiwan.toml"))
