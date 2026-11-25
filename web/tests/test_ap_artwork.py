"""Check the manufacturer's PNGs, bilateral metric maps and physical calibration."""
import json
from io import BytesIO

import numpy as np
import pytest
from PIL import Image
import pydicom

from core import planning
from core.engine import Session, index_transform
from core.scene_files import write_mrb
from check_core import synthetic_dicom


def film(tmp_path, spacing=(.8,.5), *, reverse=False):
    path = tmp_path/"phantom.dcm"
    synthetic_dicom(path, np.zeros((240,320),np.uint16))
    ds = pydicom.dcmread(path)
    if spacing is None:
        del ds.PixelSpacing
    else:
        ds.PixelSpacing = list(spacing)
    ds.ImagerPixelSpacing = [1.6,1.]
    ds.ImageOrientationPatient = [-1 if reverse else 1,0,0,0,0,-1]
    ds.save_as(path,enforce_file_format=True)
    s=Session()
    s.open(path.name,path.read_bytes())
    return s


def select(s, item, side="left", at=(120,110)):
    s.settings.pelvic_active_side=side
    c=s.controller
    c.update_derived()
    key="template_"+item["component"]
    c.planning_options({"key":key,"choice":{"id":item["id"],"angle":0.}})
    c.start(key)
    assert c.place(*at)
    return next(m for m in s.snapshot()["markups"] if m.get("artwork")==item["image"] and m["role"].startswith(side))


def shell():
    return next(v for v in planning.ITEMS.values() if v.get("image") and v["family"]=="Medacta · Mpact")


skip_art=pytest.mark.skipif(not planning.ARTWORK,reason="Optional manufacturer artwork not installed")


@skip_art
def test_all_artwork_handedness_scale_and_pivots():
    from hashlib import sha256
    checked=set()
    for item in planning.ITEMS.values():
        if "image" not in item:
            continue
        if item["image"] not in checked:
            raw=planning.artwork_bytes(item["image"])
            assert sha256(raw).hexdigest()==item["image"]
            with Image.open(BytesIO(raw)) as im:
                assert list(im.size)==item["pixels"]
            checked.add(item["image"])
        for side in (("left","right") if item["side"]=="both" else (item["side"],)):
            choice=planning.template_choice(item["component"],{"id":item["id"],"angle":0},side)
            a,b,c,d=np.array(planning.outline(choice,[3,4,0],side,[1,0,0],[0,1,0],1.25))
            x,y=(b-a)/item["pixels"][0],(d-a)/item["pixels"][1]
            np.testing.assert_allclose([np.linalg.norm(x),np.linalg.norm(y)],np.array(item["pitch"])/1.25)
            np.testing.assert_allclose(a+item["pivot"][0]*x+item["pivot"][1]*y,[3,4,0])
            assert np.sign(x[0])==(1 if side==item["drawn"] else -1)
            assert y[1]<0
            np.testing.assert_allclose(c,b+d-a)
        if item["side"]!="both":
            other="left" if item["side"]=="right" else "right"
            with pytest.raises(ValueError,match="side"):
                planning.template_choice(item["component"],{"id":item["id"],"angle":0},other)
    assert len(checked)==len(planning.ARTWORK)


@skip_art
@pytest.mark.parametrize("turns,mirror",[(0,False),(0,True),(1,False),(1,True),(2,True),(3,False)])
@pytest.mark.parametrize("reverse",[False,True])
def test_dicom_scale_and_orientation_before_placement(tmp_path,turns,mirror,reverse):
    s=film(tmp_path,reverse=reverse)
    s.turns,s.mirrored=turns,mirror
    s.orient(); s.controller.update_derived()
    assert not s.controller.missing_dependencies("template_cup")
    item=shell()
    mark=select(s,item)
    orientation=index_transform(s.base_image.shape,turns,mirror)[:2,:2]
    a,b,_,d=np.array(mark["points"])@orientation.T
    widths=(b-a)*[.5,.8]
    heights=(d-a)*[.5,.8]
    assert np.sign(widths[0])==(-1 if reverse else 1)  # source drawn for the left hip
    assert heights[1]>0
    np.testing.assert_allclose(np.linalg.norm(widths),item["pixels"][0]*item["pitch"][0])
    np.testing.assert_allclose(np.linalg.norm(heights),item["pixels"][1]*item["pitch"][1])
    assert abs(widths[1])+abs(heights[0])<1e-8


@skip_art
@pytest.mark.parametrize("spacing",[(.8,.5),None,(0,0)])
def test_ball_updates_existing_templates_and_detector_needs_ball(tmp_path,spacing):
    s=film(tmp_path,spacing)
    c=s.controller
    metric=spacing==(.8,.5)
    assert bool(c.missing_dependencies("template_cup"))!=metric
    item=shell()
    if metric:
        select(s,item)
    sx,sy=s.image.spacing
    c.start("calibration")
    for xy in [(40-10/sx,50),(40,50-10/sy),(40+10/sx,50)]:
        c.place(*xy)
    assert c._calibration_scale()==pytest.approx(1.25)
    if not metric:
        select(s,item)
    mark=next(m for m in s.snapshot()["markups"] if m.get("artwork"))
    a,b,_,d=mark["points"]
    np.testing.assert_allclose(np.linalg.norm(np.subtract(b,a)*[sx,sy]),item["pixels"][0]*item["pitch"][0]/1.25)
    np.testing.assert_allclose(np.linalg.norm(np.subtract(d,a)*[sx,sy]),item["pixels"][1]*item["pitch"][1]/1.25)
    reopened=Session()
    reopened.open("test.mrb",write_mrb(s.image,c,s.case_name,s.get_settings()))
    assert reopened.scene.volume.planning_metric==metric
    np.testing.assert_allclose(next(m for m in reopened.snapshot()["markups"] if m.get("artwork"))["points"],mark["points"])


@skip_art
def test_hide_one_side_and_restore_older_bilateral_visibility(tmp_path):
    s=film(tmp_path)
    c=s.controller
    item=shell()
    select(s,item,"left"); select(s,item,"right")
    c.set_workflow_hidden("template_cup",True)
    assert [m["role"] for m in s.snapshot()["markups"] if m.get("artwork")]==["left_planningCupAnchorOutline"]
    saved=s.serialize()
    assert saved["settings"]["hidden_workflows"]==["template_cup:right"]
    saved["settings"]["hidden_workflows"]=["template_cup"]
    s.restore(saved)
    assert not any(m.get("artwork") for m in s.snapshot()["markups"])
    c.set_workflow_hidden("template_cup",False)
    assert [m["role"] for m in s.snapshot()["markups"] if m.get("artwork")]==["right_planningCupAnchorOutline"]


@skip_art
def test_previous_cup_angle_and_new_drawing_orientation():
    item=shell()
    old=planning.template_choice("cup",json.dumps({"id":item["id"],"angle":12}),"left")
    new=planning.template_choice("cup",{"id":item["id"],"angle":12},"left")
    assert old["angle"]==pytest.approx(12+np.degrees(item["sourceAngle"]))
    assert new["angle"]==12
    assert planning.template_choice("cup",json.dumps(old),"left")==old

