#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
# File       : cli.py
# Time       ：2025/10/1 12:58
# Author     ：Jago
# Email      ：huwl@hku.hk
# Description：adapted from https://github.com/warpem/warp-tm-vis/blob/main/src/warp_tm_vis/cli.py
changed line "import rich" to "from rich.console import Console"
changed line "console = rich.console.Concole()" to "console = Console()"

changed a lot of add_tomogram function
added get_absolute_particle_positions function

added --load_correlation_volumes and --bin parameters, customized many parameters for SMV dataset
"""
from enum import Enum
from pathlib import Path
from typing import Optional, List

import mrcfile
import napari
import napari.utils.notifications
import numpy as np
import starfile
# ref https://github.com/warpem/warp-tm-vis/issues/9
from rich.console import Console
import typer
from magicgui import magicgui

# .utils is for running in Linux
from .utils import (
    find_correlation_volume_file,
    update_volume_layers,
    update_particle_layer,
    update_particle_layer_withoutcc,
    get_particle_positions_and_cc,
    get_absolute_particle_positions,
    update_corvol_layers
)

console = Console()

cli = typer.Typer(add_completion=False)


@cli.command(
    no_args_is_help=True,
    help="Visualize tomograms and particles coordinates. Adapted from warp-tm-vis"
)
def warp_tm_vis(
    reconstruction_directory: Optional[Path] = typer.Option(
        None,
        '--reconstruction-directory', '-rdir',
        help="directory containing tomograms e.g. warp_tiltseries/reconstruction/deconv (if not provided, wont load tomograms)"
    ),
    matching_directory: Optional[Path] = typer.Option(
        None,
        '--matching-directory', '-mdir',
        help="directory containing particles e.g. warp_tiltseries/matching (if not provided, wont load particles)"
    ),
    tomogram_matching_pattern: Optional[str] = typer.Option(
        "*.mrc",
        '--tomogram-matching-pattern', '-tmp',
        help="tomograms matching pattern"
    ),
    particle_matching_pattern: Optional[str] = typer.Option(
        "*.star",
        '--particle-matching-pattern', '-pmp',
        help="particle matching pattern"
    ),
    correlation_volume_pattern: Optional[str] = typer.Option(
        None,
        '--correlation-volume-pattern', '-cvp',
        help="correlation volume pattern e.g. \"*_flipx_corr.mrc\" (if not provided, wont load correlation volumes)"
    ),
    bin: Optional[float] = typer.Option(
        1.0,
        '--bin', '-b',
        help="binning factor applied to both the tomogram and particle coordinates in case of Out Of Memory"
    ),
):
    load_volumes, load_particles, load_correlation_volumes = True, True, True

    if reconstruction_directory is None:
        console.log("No reconstruction directory provided -> wont load tomograms.")
        load_volumes = False
    else:
        tomogram_files = list(reconstruction_directory.glob(tomogram_matching_pattern))
        console.log(f"found {len(tomogram_files)} tomogram files")

    if matching_directory is None:
        console.log("No matching directory provided -> wont load particles.")
        load_particles = False
    else:
        particle_files = list(matching_directory.glob(particle_matching_pattern))
        console.log(f"found {len(particle_files)} particle files")

    # correlation volume files only if user provided a pattern
    correlation_volume_files: List[Path] = []
    if correlation_volume_pattern:
        correlation_volume_files = list(matching_directory.glob(correlation_volume_pattern))
        console.log(f"found {len(correlation_volume_files)} correlation volume files")
    else:
        console.log("No correlation volume pattern provided -> wont load correlation volumes.")
        load_correlation_volumes = False

    with console.status("launching napari viewer...", spinner="arc"):
        viewer = napari.Viewer(ndisplay=3)
    console.log("napari viewer launched")

    viewer.title = "Ni-TM-VIS"

    tomogram_files = [str(path) for path in tomogram_files]
    Tomogram = Enum('Tomogram', ' '.join(tomogram_files))

    @magicgui(auto_call=True)
    def add_tomogram(tomogram: Tomogram):
        # load volumes
        if load_volumes:
            console.log(f"loading tomogram from {tomogram}...")
            volume = mrcfile.read(tomogram.name)
            console.log(f"tomogram loaded")

            # voxels = volume.size
            # estimated_bytes = voxels * 4  # float32
            # if estimated_bytes > 2000000000:  # 2GB threshold
            #     console.log(f"tomogram's size too big, downsampling to uint8...")
            #     mn, mx = volume.min(), volume.max()
            #     if mx > mn:
            #         volume = ((volume - mn) / (mx - mn) * 255).astype(np.uint8)
            #     else:
            #         volume = volume.astype(np.uint8)
            if not bin == 1.0:
                console.log(f"binning coordinates to {bin}...")
                volume = volume[::bin, ::bin, ::bin]  # default: 1.0
            update_volume_layers(viewer, volume)

        if load_correlation_volumes:
            correlation_volume_file = find_correlation_volume_file(Path(tomogram.name), correlation_volume_files)
            console.log(f"loading correlation volume from {correlation_volume_file}")
            correlation_volume = mrcfile.read(correlation_volume_file)
            console.log(f"correlation volume loaded")
            update_corvol_layers(viewer, correlation_volume)

        if load_particles and load_correlation_volumes:  # load particle positions and cc values for Warp outputs
            console.log(f"loading particle metadata...")
            zyx, cc = get_particle_positions_and_cc(tomogram.name, particle_files, tomogram_matching_pattern)
            console.log(f"particle metadata loaded")
            # notify user of max cc
            ts_id = Path(tomogram.name).name
            napari.utils.notifications.show_info(f"max cc for {ts_id} is {cc.max()}")
            update_particle_layer(viewer, zyx, cc, tomogram.name)
        elif load_particles and not load_correlation_volumes:  # load particle positions for star files
            console.log(f"loading particle metadata...")
            zyx = get_absolute_particle_positions(tomogram.name, particle_files, tomogram_matching_pattern)
            console.log(f"particle metadata loaded")
            update_particle_layer_withoutcc(viewer, zyx, bin, tomogram.name)

    # create interactive widget for subsetting particles
    @magicgui(auto_call=True)
    def subset_particles(min_cc: float = 0.0):
        cc = viewer.layers['particles'].metadata['cc']
        zyx = viewer.layers['particles'].metadata['positions']
        zyx = zyx[cc >= min_cc]
        viewer.layers['particles'].data = zyx

    # add widgets for changing tomogram and subsetting particles to viewer
    viewer.window.add_dock_widget(add_tomogram, area='bottom')
    if load_correlation_volumes:
        viewer.window.add_dock_widget(subset_particles, area='bottom')

    # initialise widget and launch viewer
    add_tomogram()
    napari.run()
