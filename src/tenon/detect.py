import math
import re
import cv2
import base64
import numpy as np
from typing import Optional
from collections import namedtuple

RotateData = namedtuple("RotateData", "similar, angle, start, end, step")
MatchData = namedtuple("MatchData", "similar, inner_rotate_angle, total_rotate_angle")


def request_image_content(image_url, proxies: Optional[dict] = None):
    import requests  # type: ignore

    headers = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    }
    response = requests.get(image_url, headers=headers, proxies=proxies)
    return response.content


def set_mask(radius, check_pixel):
    center_point = (radius, radius)
    mask = np.zeros((radius * 2, radius * 2), dtype=np.uint8)
    mask = cv2.circle(mask, center_point, radius, (255, 255, 255), -1)
    mask = cv2.circle(mask, center_point, radius - check_pixel, (0, 0, 0), -1)
    return mask


def cut_image(origin_array, std, cut_value, radius=None, check_pixel=None):
    cut_pixel_list = []  # 上, 左, 下, 右
    height, width = origin_array.shape[:2]
    if not radius:
        for rotate_count in range(4):
            cut_pixel = 0
            rotate_array = np.rot90(origin_array, rotate_count)
            for line in rotate_array:
                if len(line.shape) == 1:
                    pixel_set = set(list(line)) - {0, 255}
                else:
                    pixel_set = set(map(tuple, line)) - {(0, 0, 0), (255, 255, 255)}

                if not pixel_set:
                    cut_pixel += 1
                    continue

                if len(line.shape) == 1:
                    pixels = tuple(
                        pixel
                        for pixel in tuple(pixel_set)
                        if cut_value <= pixel <= 255 - cut_value
                    )
                    pixel_std = np.std(pixels)
                    if pixel_std > std:
                        break
                else:
                    count = 0
                    pixels = [[], [], []]
                    for b, g, r in pixel_set:
                        if cut_value <= min(b, g, r) <= max(b, g, r) <= 255 - cut_value:
                            pixels[0].append(b)
                            pixels[1].append(g)
                            pixels[2].append(r)

                    bgr_std = tuple(
                        np.std(pixels[i]) if pixels[i] else 0 for i in range(3)
                    )
                    for pixel_std in bgr_std:
                        if pixel_std >= std:
                            count += 1
                    if count == 3:
                        break
                cut_pixel += 1
            cut_pixel_list.append(cut_pixel)
        cut_pixel_list[2] = height - cut_pixel_list[2]
        cut_pixel_list[3] = width - cut_pixel_list[3]

    elif check_pixel:
        y, x = height // 2, width // 2
        resize_check_pixel = math.ceil(radius / (radius - check_pixel) * check_pixel)
        for i in -1, 1:
            for p in y, x:
                pos = p + i * radius
                for _ in range(p - radius):
                    p_x, p_y = (pos, y) if len(cut_pixel_list) % 2 else (x, pos)
                    pixel_point = origin_array[p_y][p_x]
                    pixel_set = (
                        {pixel_point} - {0, 255}
                        if isinstance(pixel_point, np.uint8)
                        else set(tuple(pixel_point)) - {(0, 0, 0), (255, 255, 255)}
                    )
                    if not pixel_set:
                        pos += i
                        continue
                    status = True
                    for pixel in pixel_set:
                        if pixel <= cut_value or pixel >= 255 - cut_value:
                            status = False
                            break
                    if status:
                        break
                    pos += i
                cut_pixel_list.append(pos + i * resize_check_pixel)

    up, left, down, right = cut_pixel_list
    cut_array = origin_array[up:down, left:right]
    diameter = (radius or min(cut_array.shape[:2]) // 2) * 2
    cut_result = cv2.resize(cut_array, dsize=(diameter, diameter))
    return cut_result


def mask_image(origin_array, check_pixel):
    radius = origin_array.shape[0] // 2
    mask = set_mask(radius, check_pixel)
    src_array = np.zeros(origin_array.shape, dtype=np.uint8)
    mask_result = cv2.add(origin_array, src_array, mask=mask)
    return mask_result


def mask_outer_image(origin_array, check_pixel):
    height, width = origin_array.shape[:2]

    # 找到黑色圆圈的半径
    # 对于灰度图像和彩色图像分别处理
    if len(origin_array.shape) == 2:
        # 灰度图像
        black_pixels = np.where(origin_array == 0)
    else:
        # 彩色图像
        black_pixels = np.where((origin_array == [0, 0, 0]).all(axis=2))

    # 计算黑色区域的边界
    if len(black_pixels[0]) > 0:
        y_min, y_max = np.min(black_pixels[0]), np.max(black_pixels[0])
        x_min, x_max = np.min(black_pixels[1]), np.max(black_pixels[1])

        # 计算黑色圆圈的半径
        black_radius = max((y_max - y_min), (x_max - x_min)) // 2
        center_y = (y_max + y_min) // 2
        center_x = (x_max + x_min) // 2
    else:
        # 如果没有找到黑色像素，使用默认值
        black_radius = min(height, width) // 2
        center_y, center_x = height // 2, width // 2

    # 创建mask
    mask = np.zeros((height, width), dtype=np.uint8)
    center_point = (center_x, center_y)

    # 使用黑色圆圈的半径加上check_pixel作为外圆半径
    outer_radius = black_radius + check_pixel
    # 使用黑色圆圈的半径作为内圆半径
    inner_radius = black_radius

    # 画外圆
    cv2.circle(mask, center_point, outer_radius, (255, 255, 255), -1)
    # 画内圆
    cv2.circle(mask, center_point, inner_radius, (0, 0, 0), -1)

    # 创建与原图相同维度的零矩阵
    if len(origin_array.shape) == 3:
        src_array = np.zeros((height, width, 3), dtype=np.uint8)
    else:
        src_array = np.zeros((height, width), dtype=np.uint8)

    # 使用mask进行操作
    mask_result = cv2.add(origin_array, src_array, mask=mask)
    return mask_result

def rotate_image(inner_image, outer_image, anticlockwise):
    rtype = int(anticlockwise) or -1
    h, w = inner_image.shape[:2]
    center = (h * 0.5, w * 0.5)
    
    # 优化模板匹配方法及权重
    methods = [
        (cv2.TM_CCOEFF_NORMED, 0.5),  # 降低相关系数匹配的权重
        (cv2.TM_CCORR_NORMED, 0.3),   # 降低相关匹配的权重
        (cv2.TM_SQDIFF_NORMED, 0.2)   # 增加平方差匹配的权重
    ]
    total_weight = sum(weight for _, weight in methods)
    
    # 第一阶段：粗搜索（步长减小到2度，提高初始精度）
    best_angle = 0
    max_similar = 0
    
    for angle in range(0, 360, 2):  # 步长从3改为2
        mat_rotate = cv2.getRotationMatrix2D(center, rtype * angle, 1)
        dst = cv2.warpAffine(inner_image, mat_rotate, (h, w))
        
        similar_sum = 0
        for method, weight in methods:
            ret = cv2.matchTemplate(outer_image, dst, method)
            if method == cv2.TM_SQDIFF_NORMED:
                similar_sum += (1.0 - cv2.minMaxLoc(ret)[0]) * weight
            else:
                similar_sum += cv2.minMaxLoc(ret)[1] * weight
        
        similar_value = similar_sum / total_weight
        if similar_value > max_similar:
            max_similar = similar_value
            best_angle = angle
    
    # 第二阶段：中等精度搜索（扩大搜索范围到±4度）
    second_start = max(0, best_angle - 4)
    second_end = min(360, best_angle + 4)
    for angle in np.arange(second_start, second_end, 0.2):  # 步长从0.3改为0.2
        mat_rotate = cv2.getRotationMatrix2D(center, rtype * angle, 1)
        dst = cv2.warpAffine(inner_image, mat_rotate, (h, w))
        
        similar_sum = 0
        for method, weight in methods:
            ret = cv2.matchTemplate(outer_image, dst, method)
            if method == cv2.TM_SQDIFF_NORMED:
                similar_sum += (1.0 - cv2.minMaxLoc(ret)[0]) * weight
            else:
                similar_sum += cv2.minMaxLoc(ret)[1] * weight
        
        similar_value = similar_sum / total_weight
        if similar_value > max_similar:
            max_similar = similar_value
            best_angle = angle
    
    # 第三阶段：高精度搜索（扩大搜索范围到±0.4度）
    fine_start = max(0, best_angle - 0.4)
    fine_end = min(360, best_angle + 0.4)
    best_match = RotateData(max_similar, best_angle, 0, 360, 0.02)
    
    for angle in np.arange(fine_start, fine_end, 0.02):  # 步长从0.05改为0.02
        mat_rotate = cv2.getRotationMatrix2D(center, rtype * angle, 1)
        dst = cv2.warpAffine(inner_image, mat_rotate, (h, w))
        
        similar_sum = 0
        for method, weight in methods:
            ret = cv2.matchTemplate(outer_image, dst, method)
            if method == cv2.TM_SQDIFF_NORMED:
                similar_sum += (1.0 - cv2.minMaxLoc(ret)[0]) * weight
            else:
                similar_sum += cv2.minMaxLoc(ret)[1] * weight
        
        similar_value = similar_sum / total_weight
        if similar_value > best_match.similar:
            best_match = RotateData(similar_value, angle, fine_start, fine_end, 0.02)
    
    return best_match


def image_to_cv2(base_image: str, image_type: int, grayscale: bool, proxies=None):
    assert image_type in [0, 1, 2]
    if image_type == 0:
        search_base64 = re.search("base64,(.*?)$", base_image)
        base64_image = search_base64.group(1) if search_base64 else base_image
        image_array = np.asarray(
            bytearray(base64.b64decode(base64_image)), dtype="uint8"
        )
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    elif image_type == 1:
        image_content = request_image_content(base_image, proxies)
        if not image_content:
            raise Exception("请求图片链接失败！")
        image_array = np.array(bytearray(image_content), dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    else:
        image = cv2.imread(base_image)

    if grayscale:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    return image


def rotate_identify(
    small_circle: str,
    big_circle: str,
    image_type: int = 0,
    check_pixel: int = 10,
    speed_ratio: float = 1,
    grayscale: bool = False,
    anticlockwise: bool = False,
    standard_deviation: int = 0,
    cut_pixel_value: int = 0,
    proxies: Optional[dict] = None,
) -> MatchData:
    """
    双图旋转类型滑块验证码识别
    :param small_circle: 小圈图片
    :param big_circle: 大圈图片
    :param image_type: 图片类型: 0: 图片base64; 1: 图片url; 2: 图片文件地址
    :param grayscale: 是否需要灰度化处理: True: 是; False: 否
    :param check_pixel: 进行图片验证的像素宽度
    :param speed_ratio: 小圈与大圈的转动速率比: 小圈转动360度时/大圈转动的角度
    :param grayscale: 是否需要灰度化处理: True: 是; False: 否
    :param anticlockwise: 图片旋转的类型: True: 小圈逆时针; False: 小圈顺时针
    :param standard_deviation: 计算行/列像素点值的标准差
    :param cut_pixel_value: 需要裁切的像素点值; 保留值区间range(cut_pixel_value, 255 - cut_pixel_value)
    :param proxies: 代理
    :return: namedtuple -> MatchData
    """
    inner_image = image_to_cv2(small_circle, image_type, grayscale, proxies)
    outer_image = image_to_cv2(big_circle, image_type, grayscale, proxies)

    cut_inner_image = cut_image(inner_image, standard_deviation, cut_pixel_value)
    cut_inner_radius = cut_inner_image.shape[0] // 2
    cut_outer_image = cut_image(
        outer_image, standard_deviation, cut_pixel_value, cut_inner_radius, check_pixel
    )

    inner_annulus = mask_image(cut_inner_image, check_pixel)
    outer_annulus = mask_outer_image(cut_outer_image, check_pixel)

    rotate_info = rotate_image(inner_annulus, outer_annulus, anticlockwise)
    inner_angle = round(rotate_info.angle * speed_ratio / (speed_ratio + 1), 2)
    return MatchData(rotate_info.similar, inner_angle, rotate_info.angle)


def notch_identify(
    slider: str,
    background: str,
    image_type: int = 0,
    color_type: bool = True,
    proxies: Optional[dict] = None,
):
    """
    缺口图片验证码识别
    :param slider: 滑块图片
    :param background: 背景图片
    :param image_type: 图片类型: 0: 图片base64; 1: 图片url; 2: 图片文件地址
    :param color_type: 是否需要灰度化处理: True: 是; False: 否
    :param proxies: 代理, 用于请求图片url链接
    :return: 缺口x轴像素间距
    """
    slider_img = image_to_cv2(slider, image_type, color_type, proxies)
    background_img = image_to_cv2(background, image_type, color_type, proxies)
    background_edge = cv2.Canny(background_img, 100, 200)
    slider_edge = cv2.Canny(slider_img, 100, 200)
    background_pic = cv2.cvtColor(background_edge, cv2.COLOR_GRAY2RGB)
    slider_pic = cv2.cvtColor(slider_edge, cv2.COLOR_GRAY2RGB)
    res = cv2.matchTemplate(background_pic, slider_pic, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    return max_loc[0]


def rotate_identify_and_show_image(
    small_circle: str,
    big_circle: str,
    image_type: int = 0,
    check_pixel: int = 10,
    grayscale: bool = False,
    anticlockwise: bool = False,
    standard_deviation: int = 0,
    cut_pixel_value: int = 0,
    image_show_time: int = 0,
    image_add: bool = False,
    proxies: Optional[dict] = None,
):
    """
    双图旋转类型滑块验证码识别
    :param small_circle: 小圈图片
    :param big_circle: 大圈图片
    :param image_type: 图片类型: 0: 图片base64; 1: 图片url; 2: 图片文件地址
    :param grayscale: 是否需要灰度化处理: True: 是; False: 否
    :param check_pixel: 进行图片验证的像素宽度
    :param anticlockwise: 图片旋转的类型: True: 小圈逆时针; False: 小圈顺时针
    :param standard_deviation: 计算行/列像素点值的标准差, 标准差设置过大会造成图片被完全裁切
    :param cut_pixel_value: 需要裁切的像素点值; 保留值区间range(cut_pixel_value, 255 - cut_pixel_value)
    :param image_show_time: 调试下显式图片时间, 默认常态显式
    :param image_add: 旋转后的内外圈图片叠加显示
    :param proxies: 代理
    :return: namedtuple -> MatchData
    """
    inner_image = image_to_cv2(small_circle, image_type, grayscale, proxies)
    outer_image = image_to_cv2(big_circle, image_type, grayscale, proxies)

    cut_inner_image = cut_image(inner_image, standard_deviation, cut_pixel_value)
    cut_inner_radius = cut_inner_image.shape[0] // 2
    cut_outer_image = cut_image(
        outer_image, standard_deviation, cut_pixel_value, cut_inner_radius, check_pixel
    )

    cv2.imshow("cut_inner_image", cut_inner_image)
    cv2.imshow("cut_outer_image", cut_outer_image)

    inner_annulus = mask_image(cut_inner_image, check_pixel)
    outer_annulus = mask_outer_image(cut_outer_image, check_pixel)
    # outer_annulus = cv2.resize(outer_annulus, inner_annulus.shape[:2])

    cv2.imshow("inner_annulus", inner_annulus)
    cv2.imshow("outer_annulus", outer_annulus)
    rotate_info = rotate_image(inner_annulus, outer_annulus, anticlockwise)
    height, width = cut_inner_image.shape[:2]
    rotate_angle = rotate_info.angle * (int(anticlockwise) or -1)
    mat_rotate = cv2.getRotationMatrix2D((height * 0.5, width * 0.5), rotate_angle, 1)
    rotated_inner_image = cv2.warpAffine(cut_inner_image, mat_rotate, (height, width))

    cv2.imshow("cut_outer_image", cut_outer_image)
    cv2.imshow("outer_image", outer_image)
    cv2.imshow("rotated_inner_image", rotated_inner_image)

    if image_add:
        origin_h, origin_w = inner_image.shape[:2]
        mat_rotate = cv2.getRotationMatrix2D(
            (origin_h // 2, origin_w // 2), rotate_angle, 1
        )
        rotated_origin_inner_image = cv2.warpAffine(
            inner_image, mat_rotate, inner_image.shape[:2]
        )
        inner_mask = cv2.circle(
            np.zeros(inner_image.shape[:2], dtype=np.uint8),
            (origin_h // 2, origin_w // 2),
            height // 2,
            (255, 255, 255),
            -1,
        )
        outer_mask = set_mask(origin_h // 2, origin_w // 2 - height // 2)

        sad = cv2.add(
            rotated_origin_inner_image,
            np.zeros(outer_image.shape, dtype=np.uint8),
            mask=inner_mask,
        )
        sad2 = cv2.add(
            outer_image, np.zeros(outer_image.shape, dtype=np.uint8), mask=outer_mask
        )

        image_add_view = cv2.add(sad, sad2)
        cv2.imshow("image_add", image_add_view)
    cv2.waitKey(image_show_time * 1000)