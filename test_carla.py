# CARLA TESTING MODULE
# Developed by : EL HANNACH Walid

# Import necessary libraries
import glob #it helps locate the CARLA module based on the Python version and OS.
import os #Provides a way to interact with the operating system
import sys #Used here to append the CARLA module path to the system path.
import time #Used for pausing the script and controlling the loop

# Overview:
# This script initializes a CARLA simulation, spawns a vehicle at a specified location,
# and configures it with certain traffic management settings. It allows user interaction
# to stop the vehicle and activate hazard lights.

# Add CARLA module to path
try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla

def main():
    """
    Main function to run our simulation.
    """
    try:
        # Connect to the CARLA server
        client = carla.Client('localhost', 2000)
        client.set_timeout(10.0)  # Set timeout for client requests

        # Get the world and blueprint library
        world = client.get_world()
        blueprint_library = world.get_blueprint_library()

        # Destroy all existing vehicle actors in the world
        actors = world.get_actors().filter('vehicle.*')
        for actor in actors:
            actor.destroy()

        # Get blueprint for the first vehicle in the blueprint library
        vehicle_bp = blueprint_library.filter('vehicle.*')[0]

        # Get spawn points from the world map
        spawn_points = world.get_map().get_spawn_points()

        # Define a specific location to use for vehicle spawning
        roundabout_location = carla.Location(x=85.5, y=-4.7, z=0.0)
        # Choose the closest spawn point to the defined location
        spawn_point = min(spawn_points, key=lambda sp: sp.location.distance(roundabout_location))

        # Spawn the vehicle at the selected spawn point
        vehicle = world.spawn_actor(vehicle_bp, spawn_point)

        # Namming the vehicle as "Capgemini Engineering vehicle"
        vehicle_name = "Engineering project"
        print(f"Vehicle spawned with custom name: {vehicle_name}")

        # Enable autopilot for the vehicle
        vehicle.set_autopilot(True)

        # Configure the traffic manager settings
        traffic_manager = client.get_trafficmanager(8000)
        traffic_manager.set_global_distance_to_leading_vehicle(2.0)  # Set the following distance
        traffic_manager.ignore_lights_percentage(vehicle, 0)  # Vehicle will follow traffic lights
        traffic_manager.auto_lane_change(vehicle, True)  # Allow automatic lane changes
        traffic_manager.vehicle_percentage_speed_difference(vehicle, 0)  # No speed difference

        try:
            while True:
                # Prompt user to stop the vehicle
                user_input = input("Voulez-vous arrêter la voiture? (Entrez 'v' pour arrêter): ").strip().lower()
                if user_input == 'v':
                    # Apply hand brake and full brake to stop the vehicle
                    vehicle.apply_control(carla.VehicleControl(hand_brake=True, brake=1.0))
                    vehicle.set_autopilot(False)  # Disable autopilot

                    # Activate hazard lights
                    light_state = carla.VehicleLightState(carla.VehicleLightState.Position | 
                                                          carla.VehicleLightState.LeftBlinker | 
                                                          carla.VehicleLightState.RightBlinker)
                    vehicle.set_light_state(light_state)
                    print("Vehicle stopped and hazard lights activated.")
                    break

                time.sleep(0.5)  # Wait before re-prompting user
        except KeyboardInterrupt:
            print("Stopping simulation...")

    finally:
        # Clean up the vehicle actor if it exists
        if 'vehicle' in locals():
            vehicle.destroy()
        print("Cleaned up vehicle.")

# Entry point of the script
if __name__ == '__main__':
    main()
