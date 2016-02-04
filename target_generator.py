from __future__ import division

import numpy as np
import data_container
import util


class TargetGenerator(object):
    def __init__(self):
        self._dof_values_currrent_target = None
        self.num_images = None

    def get_target(self):
        raise NotImplementedError

    def get_dof_values_current_target(self):
        """
        Returns ground truth dof values for the current target (i.e. the one that get_target() returned last time it was called)
        """
        return self._dof_values_currrent_target


class SimulatorTargetGenerator(TargetGenerator):
    def __init__(self, sim, num_images):
        super(SimulatorTargetGenerator, self).__init__()
        self.sim = sim
        self.num_images = num_images

    def get_target(self):
        """
        Changes the state of the sim as a side effect but restores it
        """
        dof_values = self.sim.dof_values
        self._dof_values_currrent_target = self._get_dof_values_target()
        self.sim.reset(self._dof_values_currrent_target)
        image_target = self.sim.observe()
        self.sim.reset(dof_values) # restore
        return image_target, self._dof_values_currrent_target

    def _get_dof_values_target(self):
        """
        Generates new ground truth dof values for the target
        """
        raise NotImplementedError()


class RandomTargetGenerator(SimulatorTargetGenerator):
    def _get_dof_values_target(self):
        return self.sim.sample_state()


class OgreNodeTargetGenerator(SimulatorTargetGenerator):
    def __init__(self, sim, num_images, node_name=None, relative_pos=None):
        super(OgreNodeTargetGenerator, self).__init__(sim, num_images)
        self.node_name = node_name or 'ogrehead'
        self.relative_pos = relative_pos or np.array([6., 0, 0])

    def get_dof_values_current_target(self):
        node_pos = self.sim.ogre.getNodePosition(self.node_name)
        camera_pos = node_pos + self.relative_pos
        pos_angle = np.zeros(min(6, self.sim.state_dim))
        pos_angle[:min(3, self.sim.state_dim)] = camera_pos[:min(3, self.sim.state_dim)]
        return pos_angle

    def _get_dof_values_target(self):
        dof_values_current_target = self.get_dof_values_current_target()
        dof_values_current_target[:3] += np.random.random(3) - 0.5 # relatively the same plus some noise
        return dof_values_current_target


class NegativeOgreNodeTargetGenerator(OgreNodeTargetGenerator):
    def get_target(self):
        dof_values = self.sim.dof_values
        self._dof_values_currrent_target = self._get_dof_values_target()
        self.sim.reset(self._dof_values_currrent_target)
        node_pos = self.sim.ogre.getNodePosition(self.node_name)
        self.sim.ogre.setNodePosition(self.node_name, np.array([self.sim.dof_values[0] + 10.] + node_pos.tolist()[1:]))
        image_target = self.sim.observe()
        self.sim.ogre.setNodePosition(self.node_name, node_pos)
        self.sim.reset(dof_values) # restore
        return image_target, self._dof_values_currrent_target


class DataContainerTargetGenerator(TargetGenerator):
    def __init__(self, fname, image_transformer=None):
        super(DataContainerTargetGenerator, self).__init__()
        try:
            self.container = data_container.ImageTrajectoryDataContainer(fname)
            self.num_images = self.container.num_trajs
        except ValueError:
            self.container = data_container.DataContainer(fname)
            self.num_images = self.container.num_data
        self.image_iter = 0
        self.image_transformer = image_transformer

    def get_target(self):
        datum_names = ['image_target', 'pos']
        if isinstance(self.container, data_container.TrajectoryDataContainer):
            image_target, self._dof_values_currrent_target = self.container.get_datum(self.image_iter, 0, datum_names).values()
        else:
            image_target, self._dof_values_currrent_target = self.container.get_datum(self.image_iter, datum_names).values()
        self.image_iter += 1
        if self.image_transformer:
            image_target = self.image_transformer.transform(image_target)
        return image_target, self._dof_values_currrent_target


class InteractiveTargetGenerator(SimulatorTargetGenerator):
    def __init__(self, sim, num_images, vis_scale=1):
        super(InteractiveTargetGenerator, self).__init__(sim, num_images)
        self.vis_scale = vis_scale

    def _get_dof_values_target(self):
        dof_vel_min, dof_vel_max = self.sim.dof_vel_limits
        while True:
            image = self.sim.observe()
            _, exit_request, key = util.visualize_images_callback(image, window_name="Interactive target window", vis_scale=self.vis_scale, delay=100, ret_key=True)
            if exit_request:
                raise KeyboardInterrupt # something else should be raised
            vel = np.zeros(self.sim.state_dim)
            if key == 81: # left arrow
                vel[0] = dof_vel_min[0]
            elif key == 82: # up arrow
                vel[1] = dof_vel_max[1]
            elif key == 83: # right arrow
                vel[0] = dof_vel_max[0]
            elif key == 84: # down arrow
                vel[1] = dof_vel_min[1]
            elif key == 32: # space
                break
            self.sim.apply_action(vel)
        return self.sim.state
