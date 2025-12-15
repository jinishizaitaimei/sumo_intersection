"""
当前版本能够实现：
    1. 雨天、雪天、雾霾天
    2. 事故车设置：设置事故车的停止时间、事故车辆的数量等。车辆会绕行与重新路由
    3. 紧急车辆的设置，其能够产生更加积极的变道
    4. 车道禁用，事故车所在的车道可以设置为车道禁用。当然你也可以不用将事故车辆的车道作为禁用车道，自行设置那个车道是禁用车道
    5. 车辆在每个车道出现的具体数量
当前版本未能实现：
    1. 用户自行设计随机种子和.net的信号灯配时
    2. 公交车与公交专用车道未能实现，原因:天府三街不存在公交专用车道，同时公交车运行线路与间隔时间也未知
    3. 车道管制未实现，即目前是整个车道禁用，而不是一小段路线禁用
    4. 紧急车辆未设置闯红灯权限
一些说明见下文todo和注释
"""
import xml.etree.ElementTree as ET
import random
import numpy as np


# 自定义缩进函数（兼容Python 3.8及以下版本）
def indent(elem, level=0, space="    "):
    """自定义缩进函数，用于美化XML输出"""
    i = "\n" + level * space
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + space
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for subelem in elem:
            indent(subelem, level + 1, space)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def generate_vehicle_type(parent_element, type_id, **params):
    """生成车辆类型定义。params可接收accel, decel, length, maxSpeed等参数。"""
    default_params = {
        "accel": "0.8",
        "decel": "4.5",
        "sigma": "0.5",
        "length": "5",
        "maxSpeed": "70",
        "color": "1,1,0"  # 默认颜色为黄色
    }
    # 用传入的参数覆盖默认参数
    default_params.update(params)
    vtype = ET.SubElement(parent_element, "vType", id=type_id, **default_params)
    return vtype


def generate_route(parent_element, route_id, edges):
    """生成路线定义。"""
    route = ET.SubElement(parent_element, "route", id=route_id, edges=edges)
    return route


def main():
    # 创建XML根元素
    root = ET.Element("routes")
    #todo 环境分为雨天。雪天、雾霾天。在这里可以通过修改accel、decel、maxSpeed、minGap等参数来达到不同的环境，这里的修改都是相对的。（这几个目前默认，未添加"minGap": "1.5",  # 激进驾驶员，车辆间距更小 "tau": "0.8", # 反应更快 "sigma": "0.8" # 更激进, 此外跟车模型和变道模型也可设置）
    #文档见 https://sumo.dlr.de/docs/Definition_of_Vehicles%2C_Vehicle_Types%2C_and_Routes.html#abstract_vehicle_class
    # 1. 定义多种车辆类型（可随机选择）
    type_params = [
        {"type_id": "car", "accel": "2.5", "decel": "4.5", "length": "4", "maxSpeed": "33.33", "color": "255,255,0"},
        # 添加紧急车辆类型
        {"type_id": "emergency", "vClass":"emergency", "accel": "5.0", "decel": "8.0", "length": "5", "maxSpeed": "50.0",
         "color": "255,0,0", "sigma": "0.0", "guiShape": "emergency",
         "lcStrategic": "2.0", "lcCooperative": "1.0", "lcSpeedGain": "3.0",  # 更积极的变道行为
         "minGap": "1.0","has.bluelight.device":"true"},  # 更小的最小间距,蓝关灯设置参见 https://sumo.dlr.de/docs/Vehicle_Type_Parameter_Defaults.html 和 https://sumo.dlr.de/docs/Simulation/Emergency.html，有了它能权限更高（包括但不限于闯红灯）
        # 添加事故车辆类型
        {"type_id": "accident", "vClass":"truck", "accel": "2.5", "decel": "4.5", "length": "4", "maxSpeed": "33.33",
         "color": "255,128,0", "sigma": "0.0", "guiShape": "truck",  # 使用货车形状表示事故车
         "minGap": "0.0", "emergencyDecel": "9.0"}
    ]
    vehicle_types = []
    for params in type_params:
        vehicle_types.append(generate_vehicle_type(root, **params))

    # 2. 定义多条路线
    route_definitions = [
        {"route_id": "ntos", "edges": "-E3 E1"},
        {"route_id": "ntow", "edges": "-E3 E2"},
        {"route_id": "ntoe", "edges": "-E3 E0"},
        {"route_id": "ston", "edges": "-E1 E3"},
        {"route_id": "stow", "edges": "-E1 E2"},
        {"route_id": "stoe", "edges": "-E1 E0"},
        {"route_id": "wtoe", "edges": "-E2 E0"},
        {"route_id": "wton", "edges": "-E2 E3"},
        # {"route_id": "wtos", "edges": "-E2 E1"},
        {"route_id": "etow", "edges": "-E0 E2"},
        {"route_id": "eton", "edges": "-E0 E3"},
        {"route_id": "etos", "edges": "-E0 E1"}
    ]
    route_edges = {}  # 存储路线ID和对应的edges
    for route_def in route_definitions:
        generate_route(root, **route_def)
        route_edges[route_def["route_id"]] = route_def["edges"]

    # 3. 定义车辆生成参数
    num_vehicles = 100  # 要生成的车辆总数
    depart_time = 0  # 初始出发时间
    base_depart_interval = 1.0  # 基础出发间隔（秒）
    interval_std_dev = 0.25  # 出发间隔的标准差，用于随机化

    # 紧急车辆参数
    emergency_vehicles = [
        {"time": 30.0, "route": "ntos", "type": "emergency"},  # 30秒时生成紧急车辆
        {"time": 60.0, "route": "ston", "type": "emergency"},  # 60秒时生成紧急车辆
        {"time": 90.0, "route": "wtoe", "type": "emergency"},  # 90秒时生成紧急车辆
    ]
    emergency_vehicles.sort(key=lambda x: x["time"])  # 按时间排序
    next_emergency_idx = 0  # 下一个要生成的紧急车辆索引

    # 事故车辆参数
    # 格式: {"time": 事故车辆生成时间, "route": 路线, "accident_start": 事故开始时间, "accident_end": 事故结束时间}
    accident_vehicles = [
        {"time": 40.0, "route": "ston", "type": "accident",
         "accident_start": 45.0, "accident_end": 75.0},  # 40秒生成，45-75秒事故
        # {"time": 80.0, "route": "wtoe", "type": "accident",
        #  "accident_start": 85.0, "accident_end": 115.0},  # 80秒生成，85-115秒事故
    ]
    accident_vehicles.sort(key=lambda x: x["time"])  # 按时间排序
    next_accident_idx = 0  # 下一个要生成的事故车辆索引

    # 4. 定义不同路线的车辆生成概率
    # 格式: {路线ID: 概率}
    route_probabilities = {
        "ntos": 0.1,  # 10%的车辆
        "ntow": 0.1,
        "ntoe": 0.1,
        "ston": 0.1,
        "stow": 0.1,
        "stoe": 0.1,
        "wtoe": 0.1,
        "wton": 0.1,
        "etow": 0.1,
        "eton": 0.05,  # 5%的车辆
        "etos": 0.05  # 5%的车辆
    }
    # 验证概率总和为1
    prob_sum = sum(route_probabilities.values())
    if abs(prob_sum - 1.0) > 0.0001:
        print(f"警告: 路线概率总和为{prob_sum}，不等于1.0，将自动归一化")
        # 归一化处理
        for route_id in route_probabilities:
            route_probabilities[route_id] /= prob_sum

    # 准备用于random.choices的参数
    route_ids = list(route_probabilities.keys())
    route_weights = list(route_probabilities.values())

    # 车辆计数
    vehicle_id = 0
    emergency_count = 0
    accident_count = 0

    # 记录每个车辆的出发时间
    vehicle_depart_times = []

    # 5. 生成车辆
    # 总车辆数包含普通车辆、紧急车辆和事故车辆
    total_special_vehicles = len(emergency_vehicles) + len(accident_vehicles)

    for _ in range(num_vehicles + total_special_vehicles):
        # 检查是否需要生成紧急车辆
        if (next_emergency_idx < len(emergency_vehicles) and
                depart_time >= emergency_vehicles[next_emergency_idx]["time"]):
            # 生成紧急车辆
            emergency = emergency_vehicles[next_emergency_idx]
            chosen_type = emergency["type"]
            chosen_route = emergency["route"]
            emergency_time = emergency["time"]

            # 紧急车辆颜色固定为红色
            vehicle_color = "255,0,0"

            # 创建紧急车辆元素
            vehicle = ET.SubElement(root, "vehicle", attrib={
                "id": f"emergency_{emergency_count}",  # 紧急车辆特殊ID
                "type": chosen_type,
                "route": chosen_route,
                "depart": str(round(emergency_time, 2)),
                "color": vehicle_color
            })

            print(f"生成紧急车辆 {emergency_count} 在 {emergency_time} 秒，路线: {chosen_route}")
            emergency_count += 1
            next_emergency_idx += 1
            vehicle_depart_times.append(emergency_time)

            # 设置depart_time为紧急车辆生成时间，避免时间跳跃
            depart_time = max(depart_time, emergency_time)

            # 继续循环，不增加普通车辆计数
            continue

        # 检查是否需要生成事故车辆
        if (next_accident_idx < len(accident_vehicles) and
                depart_time >= accident_vehicles[next_accident_idx]["time"]):
            # 生成事故车辆
            accident = accident_vehicles[next_accident_idx]
            chosen_type = accident["type"]
            chosen_route = accident["route"]
            accident_time = accident["time"]
            accident_start = accident["accident_start"]
            accident_end = accident["accident_end"]

            # 事故持续时间和位置计算
            accident_duration = accident_end - accident_start

            # 事故车辆颜色固定为橙色
            vehicle_color = "255,128,0"

            # 创建事故车辆元素
            vehicle = ET.SubElement(root, "vehicle", attrib={
                "id": f"accident_{accident_count}",  # 事故车辆特殊ID
                "type": chosen_type,
                "route": chosen_route,
                "depart": str(round(accident_time, 2)),
                "color": vehicle_color
            })

            # 为事故车辆添加停车(stop)定义
            # 获取路线的edges
            edges = route_edges[chosen_route]
            # 假设事故发生在第一个edge的中间位置
            edge_list = edges.split()
            if edge_list:
                first_edge = edge_list[0]
                # 假设在第一个车道的中间位置停车
                # 这里我们使用默认车道"_1"，实际可能需要根据路网调整
                lane_id = f"{first_edge}_1"

                # 添加stop元素
                stop = ET.SubElement(vehicle, "stop", attrib={
                    "lane": lane_id,
                    "pos": "50",  # 在edge的50米位置停车
                    "startPos": "45",  # 实际停车开始位置
                    "endPos": "55",  # 实际停车结束位置
                    "duration": str(accident_duration),  # 停车持续时间
                    "until": str(accident_end),  # 停车直到指定时间
                    "triggered": "false",  # 不触发
                    "parking": "false",  # 不是停车
                })

                print(f"生成事故车辆 {accident_count} 在 {accident_time} 秒，路线: {chosen_route}")
                print(f"  事故时间: {accident_start}-{accident_end}秒 (持续{accident_duration}秒)")
                print(f"  事故位置: {lane_id}, 位置: 50米处")

            accident_count += 1
            next_accident_idx += 1
            vehicle_depart_times.append(accident_time)

            # 设置depart_time为事故车辆生成时间
            depart_time = max(depart_time, accident_time)

            # 继续循环，不增加普通车辆计数
            continue

        # 5. 定义车辆类型的生成概率（可选）
        # 注意：这里你尝试定义车辆类型概率，但实际上我们只定义了一种车辆类型"car"
        # 如果你有多个车辆类型，可以取消下面的代码
        # vehicle_type_probabilities = {
        #     "car": 0.9,  # 60%的小汽车
        #     "truck": 0.3,  # 30%的卡车
        #     "motorbike": 0.1,  # 10%的摩托车
        # }
        # type_ids = list(vehicle_type_probabilities.keys())
        # type_weights = list(vehicle_type_probabilities.values())

        # 生成普通车辆
        # 随机选择车辆类型（均匀分布或按指定概率）
        # chosen_type = "car"  # 普通车辆都使用car类型
        # 如果使用车辆类型概率分布，使用下面这行代码：
        # chosen_type = random.choices(type_ids, weights=type_weights, k=1)[0]

        # 由于我们只有一个车辆类型"car"，直接使用
        chosen_type = "car"

        # 按照概率分布选择路线
        chosen_route = random.choices(route_ids, weights=route_weights, k=1)[0]

        # 随机生成车辆颜色（RGB格式），但排除红色和橙色（红色保留给紧急车辆，橙色给事故车辆）
        r = random.randint(0, 200)  # 限制红色分量不超过200
        g = random.randint(0, 255)
        b = random.randint(0, 255)

        # 确保颜色不是红色(255,0,0)或橙色(255,128,0)
        while (r > 240 and g < 50 and b < 50) or (r > 240 and 100 < g < 150 and b < 50):
            r = random.randint(0, 200)
            g = random.randint(0, 255)
            b = random.randint(0, 255)

        vehicle_color = f"{r},{g},{b}"

        # 生成随机的出发间隔，使车辆出发时间不完全均匀
        depart_interval = max(0.1, np.random.normal(base_depart_interval, interval_std_dev))
        depart_time += depart_interval

        # 确保不覆盖紧急车辆的时间
        while (next_emergency_idx < len(emergency_vehicles) and
               abs(depart_time - emergency_vehicles[next_emergency_idx]["time"]) < 0.1):
            depart_time += 0.2  # 稍微推迟普通车辆，避免与紧急车辆时间冲突

        # 确保不覆盖事故车辆的时间
        while (next_accident_idx < len(accident_vehicles) and
               abs(depart_time - accident_vehicles[next_accident_idx]["time"]) < 0.1):
            depart_time += 0.2  # 稍微推迟普通车辆，避免与事故车辆时间冲突

        # 创建车辆元素
        vehicle = ET.SubElement(root, "vehicle", attrib={
            "id": str(vehicle_id),  # 车辆ID为序列号
            "type": chosen_type,
            "route": chosen_route,
            "depart": str(round(depart_time, 2)),  # 出发时间保留两位小数
            "color": vehicle_color
        })

        vehicle_id += 1
        vehicle_depart_times.append(depart_time)

        # 如果已经生成了足够多的普通车辆，跳出循环
        if vehicle_id >= num_vehicles:
            # 但可能还有紧急车辆和事故车辆需要生成
            # 先生成剩余的紧急车辆
            while next_emergency_idx < len(emergency_vehicles):
                emergency = emergency_vehicles[next_emergency_idx]
                chosen_type = emergency["type"]
                chosen_route = emergency["route"]
                emergency_time = emergency["time"]

                # 紧急车辆颜色固定为红色
                vehicle_color = "255,0,0"

                # 创建紧急车辆元素
                vehicle = ET.SubElement(root, "vehicle", attrib={
                    "id": f"emergency_{emergency_count}",
                    "type": chosen_type,
                    "route": chosen_route,
                    "depart": str(round(emergency_time, 2)),
                    "color": vehicle_color
                })

                print(f"生成紧急车辆 {emergency_count} 在 {emergency_time} 秒，路线: {chosen_route}")
                emergency_count += 1
                next_emergency_idx += 1
                vehicle_depart_times.append(emergency_time)

            # 生成剩余的事故车辆
            while next_accident_idx < len(accident_vehicles):
                accident = accident_vehicles[next_accident_idx]
                chosen_type = accident["type"]
                chosen_route = accident["route"]
                accident_time = accident["time"]
                accident_start = accident["accident_start"]
                accident_end = accident["accident_end"]

                accident_duration = accident_end - accident_start
                vehicle_color = "255,128,0"

                vehicle = ET.SubElement(root, "vehicle", attrib={
                    "id": f"accident_{accident_count}",
                    "type": chosen_type,
                    "route": chosen_route,
                    "depart": str(round(accident_time, 2)),
                    "color": vehicle_color
                })

                # 为事故车辆添加停车(stop)定义
                edges = route_edges[chosen_route]
                edge_list = edges.split()
                if edge_list:
                    first_edge = edge_list[0]
                    lane_id = f"{first_edge}_1"

                    stop = ET.SubElement(vehicle, "stop", attrib={
                        "lane": lane_id,
                        "pos": "50",
                        "startPos": "45",
                        "endPos": "55",
                        "duration": str(accident_duration),
                        "until": str(accident_end),
                        "triggered": "false",
                        "parking": "false",
                    })

                    print(f"生成事故车辆 {accident_count} 在 {accident_time} 秒，路线: {chosen_route}")
                    print(f"  事故时间: {accident_start}-{accident_end}秒 (持续{accident_duration}秒)")

                accident_count += 1
                next_accident_idx += 1
                vehicle_depart_times.append(accident_time)

            break

    # 6. 重新按出发时间排序所有车辆
    # 获取所有车辆并排序
    vehicles = root.findall("vehicle")
    # 按出发时间排序
    vehicles_sorted = sorted(vehicles, key=lambda v: float(v.get("depart")))

    # 清除原有车辆
    for vehicle in root.findall("vehicle"):
        root.remove(vehicle)

    # 按排序顺序重新添加，并重新分配ID
    for i, vehicle in enumerate(vehicles_sorted):
        vehicle.set("id", str(i))
        root.append(vehicle)

    # 7. 统计各路线实际生成的车辆数量
    route_counts = {route_id: 0 for route_id in route_ids}
    emergency_route_counts = {route_id: 0 for route_id in route_ids}
    accident_route_counts = {route_id: 0 for route_id in route_ids}

    for vehicle in root.findall("vehicle"):
        route_id = vehicle.get("route")
        vehicle_type = vehicle.get("type")

        if vehicle_type == "emergency":
            emergency_route_counts[route_id] = emergency_route_counts.get(route_id, 0) + 1
        elif vehicle_type == "accident":
            accident_route_counts[route_id] = accident_route_counts.get(route_id, 0) + 1
        else:
            route_counts[route_id] = route_counts.get(route_id, 0) + 1

    print("\n车辆分布统计:")
    print("普通车辆:")
    for route_id, count in route_counts.items():
        if count > 0:
            percentage = (count / num_vehicles) * 100
            print(f"  {route_id}: {count}辆车 ({percentage:.1f}%)")

    print(f"\n紧急车辆: 共{emergency_count}辆")
    for route_id, count in emergency_route_counts.items():
        if count > 0:
            print(f"  {route_id}: {count}辆车")

    print(f"\n事故车辆: 共{accident_count}辆")
    for route_id, count in accident_route_counts.items():
        if count > 0:
            print(f"  {route_id}: {count}辆车")
            # 打印事故详细信息
            for accident in accident_vehicles:
                if accident["route"] == route_id:
                    print(f"    事故时间: {accident['accident_start']}-{accident['accident_end']}秒")

    # 计算最早的紧急车辆和最晚的车辆时间
    if vehicle_depart_times:
        print(f"\n车辆时间统计:")
        print(f"  最早出发时间: {min(vehicle_depart_times):.2f}秒")
        print(f"  最晚出发时间: {max(vehicle_depart_times):.2f}秒")
        print(f"  仿真持续时间: {max(vehicle_depart_times) - min(vehicle_depart_times):.2f}秒")

    # 8. 将生成的XML结构写入文件
    tree = ET.ElementTree(root)
    # 使用自定义缩进函数
    indent(root)

    # 写入文件
    tree.write("generated_vehicles.rou.xml", encoding="utf-8", xml_declaration=True)
    print(
        f"\n成功生成包含 {num_vehicles} 辆普通车辆、{emergency_count} 辆紧急车辆和 {accident_count} 辆事故车辆的配置文件")
    print(f"总车辆数: {num_vehicles + emergency_count + accident_count}")
    print(f"配置文件: generated_vehicles.rou.xml")

    # 9. 创建附加配置文件，用于事故车辆的特殊行为
    create_additional_file(accident_vehicles, route_edges)


#文档见 https://sumo.dlr.de/docs/Simulation/Rerouter.html
def create_additional_file(accident_vehicles, route_edges):
    """创建附加配置文件，用于设置事故车辆的特殊行为"""
    root = ET.Element("additional")

    # 为每个事故车辆创建VSS（可变速度标志）
    for i, accident in enumerate(accident_vehicles):
        # 获取路线的第一个edge
        route_id = accident["route"]
        if route_id in route_edges:
            edges_str = route_edges[route_id]  # 例如"-E1 E3"
        else:
            print(f"警告: 路线 {route_id} 在route_edges中未找到")
            continue

        edge_list = edges_str.split()
        if not edge_list:
            print(f"警告: 路线 {route_id} 的edges为空")
            continue

        first_edge = edge_list[0]  # 第一个edge，例如"-E1"
        lane_id = f"{first_edge}_1"  # 正确："-E1_1"

        # 创建VSS区域
        vss = ET.SubElement(root, "variableSpeedSign", attrib={
            "id": f"accident_vss_{i}",
            "lanes": lane_id
        })

        # 在事故开始前，速度正常
        ET.SubElement(vss, "step", attrib={
            "time": "0.00",
            "speed": "13.89"  # 50 km/h
        })

        # 事故开始时间，速度降为0
        ET.SubElement(vss, "step", attrib={
            "time": str(accident["accident_start"]),
            "speed": "0.00"
        })

        # 事故结束时间，速度恢复正常
        ET.SubElement(vss, "step", attrib={
            "time": str(accident["accident_end"]),
            "speed": "13.89"
        })

        # 创建路侧设备
        rerouter = ET.SubElement(root, "rerouter", attrib={
            "id": f"accident_rerouter_{i}",
            "edges": first_edge  # 正确：edges="-E1"
        })

        # 在事故期间重新路由
        interval = ET.SubElement(rerouter, "interval", attrib={
            "begin": str(accident["accident_start"]),
            "end": str(accident["accident_end"])
        })

        # 关闭车道
        #todo 注意这里不能关闭只有一个类型的车道，比如只有一个车道负责左转，那这个车道就不能关闭，因为车辆无法重新规划路由导致报错
        ET.SubElement(interval, "closingLaneReroute", attrib={
            "id": lane_id,  # 修正：属性名改为"id"
            "allow": "truck"
        })

    # 写入附加文件
    tree = ET.ElementTree(root)
    indent(root)
    tree.write("accident_config.add.xml", encoding="utf-8", xml_declaration=True)
    print(f"已创建事故配置附加文件: accident_config.add.xml")
    print("在运行SUMO时使用: sumo-gui -n your_network.net.xml -r generated_vehicles.rou.xml -a accident_config.add.xml")


if __name__ == "__main__":
    main()