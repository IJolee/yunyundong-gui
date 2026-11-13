"""生成离线合成测试数据；不登录、不上传、不修改源路线。"""
import argparse
import bisect
import copy
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def build_fixture(source, rng, randomize=False, mode='run', distance_km=2.0,
                  pace_min=5.0, pace_max=7.0, walk_pace=9.0, cadence=None, variation=None):
    if mode not in ('run', 'walk'):
        raise ValueError('运动模式必须为 run 或 walk')
    distance_km = float(distance_km)
    pace_min, pace_max, walk_pace = map(float, (pace_min, pace_max, walk_pace))
    cadence = float(cadence if cadence is not None else (120 if mode == 'walk' else 170))
    variation = float(variation if variation is not None else (0.05 if mode == 'walk' else 0.15))
    values = (distance_km, pace_min, pace_max, walk_pace, cadence, variation)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('参数必须是有限数字')
    if not 0.1 <= distance_km <= 100 or not 0 < pace_min <= pace_max <= 60 or not 0 < walk_pace <= 60:
        raise ValueError('距离须为0.1～100km，配速须为0～60分钟/km且最小值不能大于最大值')
    if not 1 <= cadence <= 300 or not 0 <= variation <= 0.5:
        raise ValueError('步频须为1～300步/分钟，节奏变化须为0～50%')
    target_m = distance_km*1000
    points = source['data']['pointsList']
    coords = [tuple(map(float, p['point'].split(','))) for p in points]
    if len(coords) < 2 or any(len(p) != 2 or not all(math.isfinite(v) for v in p)
                              or not -180 <= p[0] <= 180 or not -90 <= p[1] <= 90
                              for p in coords):
        raise ValueError('路线坐标无效')
    source_times = [float(p['runTime']) for p in points]
    source_speeds = [float(p['speed']) for p in points]
    if (not all(math.isfinite(t) for t in source_times)
            or any(b < a for a, b in zip(source_times, source_times[1:]))):
        raise ValueError('源路线累计时间必须有限且单调不减')
    if not all(math.isfinite(v) and v > 0 for v in source_speeds):
        raise ValueError('源路线逐点配速必须是有限正数')
    # 在原路线的累计距离上截取连续窗口，起终点均按原线段插值。
    stations = [0.0]
    for a, b in zip(coords, coords[1:]):
        stations.append(stations[-1]+distance(a, b))
    available = stations[-1]
    if available < target_m:
        raise ValueError(f'坐标路径只有 {available/1000:.3f} km，不足 2 km')
    start_m = rng.uniform(0, available-target_m) if randomize else 0.0
    end_m = start_m+target_m

    def sample(station):
        if station == 0:
            return coords[0], 0.0, source_times[0], source_speeds[0]
        index = max(0, min(len(coords)-2, bisect.bisect_left(stations, station)-1))
        a, b = coords[index:index+2]
        wanted = station-stations[index]
        low, high = 0.0, 1.0
        for _ in range(45):
            fraction = (low+high)/2
            coord = tuple(x+(y-x)*fraction for x, y in zip(a, b))
            if distance(a, coord) < wanted:
                low = fraction
            else:
                high = fraction
        timestamp = source_times[index]+fraction*(source_times[index+1]-source_times[index])
        speed = source_speeds[index]+fraction*(source_speeds[index+1]-source_speeds[index])
        return coord, station-start_m, timestamp, speed

    selected = [sample(start_m)]
    selected[0] = (selected[0][0], 0.0, selected[0][2], selected[0][3])
    for i, station in enumerate(stations):
        if start_m < station < end_m:
            selected.append((coords[i], station-start_m, source_times[i], source_speeds[i]))
    selected.append(sample(end_m))
    selected[-1] = (selected[-1][0], target_m, selected[-1][2], selected[-1][3])
    minimum = math.ceil(distance_km*pace_min*60)
    maximum = math.floor(distance_km*pace_max*60)
    if mode == 'run' and minimum > maximum:
        raise ValueError('指定区间内没有可用的整数秒时长，请扩大配速区间')
    duration = round(distance_km*walk_pace*60) if mode == 'walk' else rng.randint(minimum, maximum)
    pace = duration/(distance_km*60)
    # 平滑的局部节奏系数同时作用于时间增量和逐点配速，再归一化总时长。
    knot_count = 4 if mode == 'walk' else 7
    low, high = 1-variation, 1+variation
    knots = [rng.uniform(low, high) for _ in range(knot_count)] if randomize else [1.0]*knot_count
    factors = []
    for _, mileage, _, _ in selected:
        position = mileage/target_m*(len(knots)-1)
        index = min(int(position), len(knots)-2)
        blend = position-index
        factors.append(knots[index]*(1-blend)+knots[index+1]*blend)
    weighted_times = [0.0]
    for i in range(1, len(selected)):
        if mode == 'walk':
            # 走路采用平缓的配速曲线积分，不沿用源跑步的急加速、急减速。
            delta = (selected[i][1]-selected[i-1][1])*pace*60/1000
        else:
            delta = selected[i][2]-selected[i-1][2]
        weighted_times.append(weighted_times[-1]+delta*(factors[i-1]+factors[i])/2)
    if weighted_times[-1] <= 0:
        raise ValueError('截取后的源路线时长必须大于 0')
    time_scale = duration/weighted_times[-1]
    start = datetime(2000, 1, 1)  # 固定测试时间，不冒充真实运动日期
    epoch = 946684800
    output_points = []
    for index, (coord, mileage, timestamp, point_pace) in enumerate(selected):
        elapsed = round(weighted_times[index]*time_scale)
        output_points.append({
            'point': ','.join(f'{v:.12f}' for v in coord),
            # 沿用现有 pace_changer 的配速约定（分钟/km）：时间拉长则数值增大。
            # 局部变化和时间增量同步缩放，避免仅为改颜色而修改 speed。
            'speed': (pace if mode == 'walk' else point_pace)*factors[index]*time_scale,
            'runStatus': 1, 'isFence': 'Y',
            'runMileage': str(round(mileage, 6)), 'runTime': str(elapsed),
            'runStep': str(round(elapsed*cadence/60)), 'ts': str(epoch+elapsed),
        })
    # 保留原 JSON 的兼容字段及踩点元数据，不能丢成空列表。
    # 保留不等于重新验证已到达这些点；此副本仅供离线检查。
    result = copy.deepcopy(source)
    data = result['data']
    data.update({
        'recordMileage': distance_km, 'duration': duration, 'recodePace': pace,
        'recodeCadence': cadence,
        'recordStartTime': start.isoformat(' '),
        'recordEndTime': (start+timedelta(seconds=duration)).isoformat(' '),
        'pointsList': output_points,
    })
    data['strides'] = target_m/(duration*cadence/60)
    result.update(synthetic=True, purpose='offline_test_only',
                  checkpoint_metadata='preserved_from_source_not_revalidated',
                  speed_profile='source_pace_with_smooth_random_rhythm' if randomize else 'source_pace_scaled_with_timeline',
                  source_window_m={'start': start_m, 'end': end_m, 'available': available},
                  rhythm_factors=knots)
    result['motion_mode'] = mode
    if mode == 'walk':
        result['speed_profile'] = 'walking_smooth_pace_integrated_timeline'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'tasks_else/tasklist_9.json')
    parser.add_argument('--seed', type=int, default=None, help='可选，复现同一测试配速')
    args = parser.parse_args()
    with args.source.open(encoding='utf-8-sig') as f:
        fixture = build_fixture(json.load(f), random.Random(args.seed))
    folder = ROOT/'test_fixtures'
    folder.mkdir(exist_ok=True)
    target = folder/f'test_2km_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
    duration = fixture['data']['duration']
    seconds_per_km = duration/2
    print(f'测试里程：2.00 km；配速：{int(seconds_per_km//60)}分{seconds_per_km%60:04.1f}秒/km；总时长：{duration}秒')
    print(f'离线测试文件：{target}')


if __name__ == '__main__':
    main()
