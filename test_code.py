import glob
import os
import sys
import time
import math

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla

def main():
    try:
        client = carla.Client('localhost', 2000)
        client.set_timeout(10.0)
        world = client.get_world()
        blueprint_library = world.get_blueprint_library()
        actors = world.get_actors().filter('vehicle.*')
        for actor in actors:
            actor.destroy()
        vehicle_bp = blueprint_library.filter('vehicle.*')[5] 
        spawn_points = world.get_map().get_spawn_points()
        roundabout_location = carla.Location(x=85.5, y=-4.7, z=0.0)  
        spawn_point = min(spawn_points, key=lambda sp: sp.location.distance(roundabout_location))

        vehicle = world.spawn_actor(vehicle_bp, spawn_point)

        vehicle_name = "Engineering project"
        print(f"Vehicle spawned with custom name: {vehicle_name}")

        vehicle.set_autopilot(True)

        traffic_manager = client.get_trafficmanager(8000)
        traffic_manager.set_global_distance_to_leading_vehicle(2.0) 
        traffic_manager.ignore_lights_percentage(vehicle, 0) 
        traffic_manager.auto_lane_change(vehicle, True)  
        traffic_manager.vehicle_percentage_speed_difference(vehicle, 0)  

        try:
            while True:
                user_input = input("Voulez-vous arrêter la voiture? (Entrez 'v' pour arrêter): ").strip().lower()
                if user_input == 'v':
                    light_state = carla.VehicleLightState(carla.VehicleLightState.Position | 
                                                          carla.VehicleLightState.LeftBlinker | 
                                                          carla.VehicleLightState.RightBlinker)
                    vehicle.set_light_state(light_state)
                    print("Hazard lights activated.")

                    vehicle.set_autopilot(False)

                current_location = vehicle.get_location()

                target_location = carla.Location(current_location.x - 0.5, current_location.y - 1, current_location.z)

                start_time = time.time()

                while time.time() - start_time < 2.4:
                    current_location = vehicle.get_location()

                    angle_to_target = math.atan2(target_location.y - current_location.y, target_location.x - current_location.x)

                    steer = -0.2 if angle_to_target < 0 else 0.2

                    vehicle.apply_control(carla.VehicleControl(throttle=0.2, steer=steer))
                    time.sleep(0.1)

                start_time = time.time()

                while time.time() - start_time < 1.9:
                    current_location = vehicle.get_location()

                    angle_to_target = math.atan2(target_location.y - current_location.y, target_location.x - current_location.x)
                    

                    steer = -0.3

                    vehicle.apply_control(carla.VehicleControl(throttle=0.5, steer=steer))
                    time.sleep(0.1)

                    if vehicle.get_location().distance(target_location) <= 0.3:
                        break

                vehicle.apply_control(carla.VehicleControl(hand_brake=True, brake=1.0))
                print("Vehicle stopped.")

                break

            time.sleep(0.5) 

        except KeyboardInterrupt:
            print("Stopping simulation...")

    finally:
        if 'vehicle' in locals():
            print("Cleanup complete.")
            #vehicle.destroy()

if __name__ == '__main__':
    main()