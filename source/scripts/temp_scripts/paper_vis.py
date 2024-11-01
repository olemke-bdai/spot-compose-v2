# pylint: disable-all
import copy
import os
import sys

import numpy as np

import cv2
import open3d as o3d
from utils.coordinates import Pose3D
from utils.importer import Vector3dVector
from utils.docker_interfaces.mask3D_interface import get_all_item_point_clouds, get_coordinates_from_item
from utils.recursive_config import Config


def render_depth(geometries, camera):
    vis = o3d.visualization.Visualizer()
    vis.create_window(width=1920, height=1080, visible=False)
    for geom in geometries:
        vis.add_geometry(geom)

    view_control = vis.get_view_control()
    view_control.convert_from_pinhole_camera_parameters(camera, True)

    opt = vis.get_render_option()
    opt.point_size = 15.0

    # Capture depth buffer and create depth image
    depth = np.asarray(vis.capture_depth_float_buffer(True)) * 1000.0
    depth_scaled = depth.astype(np.uint16)
    image = np.asarray(vis.capture_screen_float_buffer(True))

    # Cleanup visualizer and return depth image
    vis.destroy_window()
    return depth_scaled, image


def main():
    # paths
    config = Config()
    data_path = config.get_subpath("resources")
    pcd_name = config["pre_scanned_graphs"]["high_res"]
    aligned_pcd_dir = os.path.join(data_path, "aligned_point_clouds", pcd_name)
    pre_pcd_dir = os.path.join(data_path, "prescans", pcd_name)
    pcd_path = os.path.join(aligned_pcd_dir, "scene.ply")
    icp_tform_ground_path = os.path.join(
        aligned_pcd_dir, "pose", "icp_tform_ground.txt"
    )
    intrinsics_path = os.path.join(aligned_pcd_dir, "intrinsic", "intrinsic_color.txt")
    mesh_path = os.path.join(pre_pcd_dir, "textured_output.obj")
    mesh_texture_path = os.path.join(pre_pcd_dir, "textured_output.jpg")
    mesh_texture_backup_path = os.path.join(pre_pcd_dir, "textured_output_orig.jpg")
    mask_name = config["pre_scanned_graphs"]["masked"]
    mask_path = os.path.join(data_path, "masked", mask_name)
    output_dir = os.path.join(data_path, "tmp")
    os.makedirs(output_dir, exist_ok=True)
    img_app_path = os.path.join(output_dir, "img_app_rgb.png")
    segmentation_app_path = os.path.join(output_dir, "img_app_seg.png")
    img_bird_object = os.path.join(output_dir, "bird_object.png")
    img_bird_drawer = os.path.join(output_dir, "bird_drawer.png")

    # load
    mesh_ground = o3d.io.read_triangle_mesh(mesh_path, True)
    pcd = o3d.io.read_point_cloud(pcd_path)
    icp_tform_ground = np.loadtxt(icp_tform_ground_path)
    intrinsics = np.loadtxt(intrinsics_path)[:3, :3]
    print(intrinsics)

    # initial vis
    mesh = mesh_ground.transform(icp_tform_ground)
    colored_pcds = get_all_item_point_clouds(mask_path, pcd_path)
    # o3d.visualization.draw_geometries([mesh, pcd])

    # render appetizer images
    height, width = 1020, 1440
    cambase_tform_icp = Pose3D()
    cambase_tform_icp.set_rot_from_rpy((0, -90, 90), degrees=True)
    camera_tform_cambase = Pose3D((3, 0, 1))
    camera_tform_cambase.set_rot_from_direction((-1, -1, -0.3), roll=-5, degrees=True)
    camera_tform_icp = cambase_tform_icp @ camera_tform_cambase.inverse()
    camera = o3d.camera.PinholeCameraParameters()
    camera.intrinsic = o3d.camera.PinholeCameraIntrinsic(
        width=width, height=height, intrinsic_matrix=intrinsics
    )
    camera.extrinsic = camera_tform_icp.as_matrix()
    depth, image = render_depth(
        [
            mesh,
        ],
        camera,
    )

    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    cv2.imshow("Image Title", image_rgb)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cv2.imwrite(img_app_path, image_rgb * 255)

    depth, image = render_depth([mesh, *colored_pcds], camera)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    cv2.imshow("Image Title", image_rgb)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cv2.imwrite(segmentation_app_path, image_rgb * 255)

    # render birds-eye images for watering can
    camera_tform_cambase = Pose3D((2.75, -1.5, 5))
    camera_tform_cambase.set_rot_from_direction((-0.3, 0, -1), roll=0, degrees=True)
    camera_tform_icp = cambase_tform_icp @ camera_tform_cambase.inverse()
    camera = o3d.camera.PinholeCameraParameters()
    camera.intrinsic = o3d.camera.PinholeCameraIntrinsic(
        width=width, height=height, intrinsic_matrix=intrinsics
    )
    camera.extrinsic = camera_tform_icp.as_matrix()

    item_cloud, _ = get_coordinates_from_item("trash can", mask_path, pcd_path, 0)
    item_cloud.paint_uniform_color([0, 1, 0])
    texture_image = cv2.imread(mesh_texture_path)
    cv2.imwrite(mesh_texture_backup_path, texture_image)
    factor = 0.3
    hsv = cv2.cvtColor(texture_image, cv2.COLOR_BGR2HSV)
    hsv[..., 1] = hsv[..., 1] * factor
    # Convert back to BGR
    texture_image_dimmed = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    # Save the modified image
    cv2.imwrite(mesh_texture_path, texture_image_dimmed)
    mesh_dimmed = o3d.io.read_triangle_mesh(mesh_path, True)
    mesh_dimmed = mesh_dimmed.transform(icp_tform_ground)
    cv2.imwrite(mesh_texture_path, texture_image)

    depth, image = render_depth([mesh_dimmed, item_cloud], camera)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    cv2.imshow("Image Title", image_rgb)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cv2.imwrite(img_bird_object, image_rgb * 255)

    # render birds-eye images for drawer
    camera_tform_cambase = Pose3D((4, -1.5, 5))
    camera_tform_cambase.set_rot_from_direction((-0.5, 0, -1), roll=0, degrees=True)
    camera_tform_icp = cambase_tform_icp @ camera_tform_cambase.inverse()
    camera = o3d.camera.PinholeCameraParameters()
    camera.intrinsic = o3d.camera.PinholeCameraIntrinsic(
        width=width, height=height, intrinsic_matrix=intrinsics
    )
    camera.extrinsic = camera_tform_icp.as_matrix()

    handle_center = np.array((0.38, -1.66, 0.55))
    handle_extents = np.array((0.4, 0.06, 0.06))
    handle_bbox = o3d.geometry.AxisAlignedBoundingBox()
    handle_bbox.min_bound = handle_center - 0.5 * handle_extents
    handle_bbox.max_bound = handle_center + 0.5 * handle_extents
    handle_idxs = set(handle_bbox.get_point_indices_within_bounding_box(pcd.points))
    handle_cloud = pcd.select_by_index(list(handle_idxs))
    handle_cloud.paint_uniform_color([1, 0.98, 0])

    drawer_extents = np.array((0.4, 0.45, 0.15))
    drawer_bbox = o3d.geometry.AxisAlignedBoundingBox()
    drawer_bbox.min_bound = handle_center - 0.5 * drawer_extents
    drawer_bbox.max_bound = handle_center + 0.5 * drawer_extents
    drawer_idxs = set(drawer_bbox.get_point_indices_within_bounding_box(pcd.points))
    drawer_only_idxs = handle_idxs ^ drawer_idxs
    drawer_cloud = pcd.select_by_index(list(drawer_only_idxs))
    drawer_cloud.paint_uniform_color([0.5804, 0, 0.8275])

    depth, image = render_depth([mesh_dimmed, handle_cloud, drawer_cloud], camera)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    cv2.imshow("Image Title", image_rgb)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cv2.imwrite(img_bird_drawer, image_rgb * 255)


if __name__ == "__main__":
    main()
    sys.exit(0)
