from osgeo import gdal, osr, ogr
import os

# путь до папки со снимками
path = QgsProject.instance().absolutePath() + '/data/data/'
# путь до папки со слоем кадастрового деления
path_vector = QgsProject.instance().absolutePath() + '/data/tulun/'
# получение имени файла со слоем кадастрового деления
filenames = os.listdir(path_vector)
file_name = ''
for fn in filenames:
    if fn.split('.')[-1] == 'shp':
        file_name = fn


# функция расчета индекса NDWI
def calculate_rastr(band3, band8):
    entries = []
    # 3ий канал снимка
    ras3 = QgsRasterCalculatorEntry()
    ras3.ref = band3.name() + '@1'
    ras3.raster = band3
    ras3.bandNumber = 1
    entries.append(ras3)

    # 8ой канал снимка
    ras8 = QgsRasterCalculatorEntry()
    ras8.ref = band8.name() + '@1'
    ras8.raster = band8
    ras8.bandNumber = 1
    entries.append(ras8)

    # формула расчета индекса
    formula = '("' + entries[0].ref + '" - "' + entries[1].ref + '") / ("' + entries[0].ref + '" + "' + entries[1].ref + '")'
    # путь до создаваемого растра
    path_raster = path + band3.name()[:-4] + '_NDWI.tif'
    # экземпляр класса калькулятора растров и задание его параметров
    calc = QgsRasterCalculator(formula, path_raster, 'GTiff',
                               band3.extent(), band3.width(), band3.height(), entries)
    # расчет для заданного объекта калькулятора растров
    res = calc.processCalculation()
    # справка по значениям результата калькулятора растров
    # https://api.qgis.org/api/classQgsRasterCalculator.html#abd4932102407a12b53036588893fa2cc
    if res == 7:
        print("error")
    elif res == 0:
        print("NDWI рассчитан")
    else:
        print(res)

    return path_raster


# функция расчета маски (аналогично функции расчета индекса NDWI)
def calculate_mask(band):
    entries = []
    raster = QgsRasterCalculatorEntry()
    raster.ref = band.name() + '@1'
    raster.raster = band
    raster.bandNumber = 1
    entries.append(raster)

    formula = '"' + raster.ref + '" > 0'
    path_raster = path + band.name()[:-5] + '_mask.tif'
    calc = QgsRasterCalculator(formula, path_raster,
                               'GTiff', band.extent(), band.width(), band.height(), entries)
    res = calc.processCalculation()
    if res == 7:
        print("error")
    elif res == 0:
        print("Маска рассчитана")
    else:
        print(res)

    return path_raster


# получение списка всех слоев проекта
lddLrs = QgsProject.instance().layerTreeRoot().children()
dict_layer = {}

# перебор слоев
for i in range(len(lddLrs)):
    lyr = lddLrs[i].layer()
    name = lyr.name()
    # добавление 3го и 8го каналов снимка в список, который добавляется в словарь по ключю имени снимка
    if name[-4:] == "_B03" or name[-4:] == "_B08":
        # если снимка с таким именем еще не добавлено в словарь, то создается соответствующий элемент словаря
        if dict_layer.get(name[:-4]) == None:
            entries = []
            entries.append(lyr)
            dict_layer[name[:-4]] = entries
        # если снимок с таким именем уже есть в словаре
        else:
            if dict_layer[name[:-4]][0].name()[-4:] != name[-4:]:
                dict_layer[name[:-4]].append(lyr)


# перебор всех ключей словаря
for key in dict_layer.keys():
    # проверка достаточно ли каналов для расчета индекса NDWI
    if len(dict_layer[key]) == 2:
        path_raster = ''
        # расчет индекса NDWI
        if dict_layer[key][0].name()[-1:] == "3":
            path_raster = calculate_rastr(dict_layer[key][0], dict_layer[key][1])
        else:
            path_raster = calculate_rastr(dict_layer[key][1], dict_layer[key][0])
        # добавление растра индекса NDWI в проект
        iface.addRasterLayer(path_raster, dict_layer[key][0].name()[:-4] + '_NDWI')

print("Расчет индеса NDWI выполнен")

# обновление списка всех слоев проекта
lddLrs = QgsProject.instance().layerTreeRoot().children()

# перебор слоев и добавление растров индекса NDWI в словарь в соотвествии с именем снимка
for i in range(len(lddLrs)):
    lyr = lddLrs[i].layer()
    name = lyr.name()
    if name[-5:] == '_NDWI':
        dict_layer[name[:-5]].append(lyr)


for key in dict_layer.keys():
    # проверка, что существет расчитанный NDWI для данного снимка
    if dict_layer[key][-1].name()[-5:] == "_NDWI":
        # расчет маски водной поверхности и добавление результирующего растра в проект
        path_raster = calculate_mask(dict_layer[key][-1])
        name = dict_layer[key][-1].name()[:-5] + '_mask'
        iface.addRasterLayer(path_raster, name)

        # обрезка растра маски по охвату слоя с кадастровыми кварталами и добавление результата в проект
        raster = QgsRasterLayer(path_raster, name)
        path_raster_output = path_raster[:-4] + '_clip.tif'

        vector_tulun = QgsVectorLayer(path_vector, file_name, 'ogr')
        
        params = {'INPUT': raster, 'MASK': vector_tulun, 'OUTPUT': path_raster_output}
        processing.run("gdal:cliprasterbymasklayer", params)
        iface.addRasterLayer(path_raster_output, name[:-4] + '_clip')

        # векторизация обрезанного растра и добавление результата в проект
        name_split = name.split('_')
        layer_name = ''
        for ns in name_split[:4]:
            layer_name = layer_name + ns + '_'
        
        dst_layername = path + layer_name + 'poligonize'

        processing.run("gdal:polygonize", {'INPUT': path_raster_output, 'BAND': 1,
                                           'FIELD': 'F', 'EIGHT_CONNECTEDNESS': False, 'EXTRA': '',
                                           'OUTPUT': dst_layername + '.shp'})

        iface.addVectorLayer(dst_layername + '.shp', layer_name + 'poligonize', 'ogr')

print('Векторизация водной поверхности выполнена')

# обновление списка всех слоев проекта
lddLrs = QgsProject.instance().layerTreeRoot().children()

vector_tulun = QgsVectorLayer(path_vector, file_name, 'ogr')
dp_vector_tulun = vector_tulun.dataProvider()


# перебор слоев и добавление векторизованных слоев
for i in range(len(lddLrs)):
    lyr = lddLrs[i].layer()
    name = lyr.name()
    if name[-11:] == '_poligonize':
        dict_layer[name[:-11]].append(lyr)

for key in dict_layer.keys():
    if dict_layer[key][-1].name()[-11:] == "_poligonize":
        name_layer = key.split('_')
        # удаление объектов слоя, несодержащие водяную поверхность
        layer = dict_layer[key][-1]
        layer.selectByExpression('"F"=0')
        layer.startEditing()
        layer.deleteSelectedFeatures()
        layer.commitChanges()

        # пересечение слоев водной поверхности и кадастровых кварталов с последующим добавлением результата в проект
        params = {'INPUT': path + layer.name() + '.shp', 'OVERLAY': path_vector + file_name,
                  'INPUT_FIELDS': [], 'OVERLAY_FIELDS': ['number'], 'OVERLAY_FIELDS_PREFIX': '',
                  'OUTPUT': path + layer.name()[:-10] + 'inter.shp', 'GRID_SIZE': None}
        processing.run("native:intersection", params)
        vector_inter = iface.addVectorLayer(path + layer.name()[:-10] + 'inter.shp',
                                            layer.name()[:-10] + 'inter', 'ogr')
        dict_layer[key].append(vector_inter)

        # объединение объектов по номеру кадастрового квартала
        params = {'INPUT': path + layer.name()[:-10] + 'inter.shp',
                  'FIELD': ['number'], 'SEPARATE_DISJOINT': False,
                  'OUTPUT': path + layer.name()[:-10] + 'unific.shp'}
        processing.run("native:dissolve", params)
        vector_unific = iface.addVectorLayer(path + layer.name()[:-10] + 'unific.shp',
                                             layer.name()[:-10] + 'unific', 'ogr')
        dict_layer[key].append(vector_unific)

        # добавление поля атрибута площади и его заполнение
        dp = vector_unific.dataProvider()
        dp.addAttributes([QgsField("Area", QVariant.Double)])
        vector_unific.updateFields()

        features = vector_unific.getFeatures()
        for f in features:
            geom = f.geometry()
            area: float = geom.area()

            attr = {dp.fieldNameIndex('Area'): str(area)}
            dp.changeAttributeValues({f.id(): attr})
            vector_unific.updateFields()

        # добавление поля в слой кадастровых кварталов
        # для дальнейшей записи площади водной поверхности в зависимости от даты
        dp_vector_tulun.addAttributes([QgsField(name_layer[-1][:4]+'.'+name_layer[-1][4:6]+'.'+name_layer[-1][6:8], QVariant.Double)])
        vector_tulun.updateFields()
QgsProject.instance().reloadAllLayers()

# запись площади водной поверхности в зависимости от даты в слой кадастровых кварталов
for key in dict_layer.keys():
    name_layer = key.split('_')
    features_tulun = vector_tulun.getFeatures()
    for layer in dict_layer[key]:
        if layer.name()[-6:] == 'unific':
            dp = layer.dataProvider()
            for f in features_tulun:
                n = f['number']
                features_unific = layer.getFeatures()
                area_f_u = 0
                for f_u in features_unific:
                    if f_u['number'] == n:
                        area_f_u += f_u['Area']
                attr = {dp_vector_tulun.fieldNameIndex(name_layer[-1][:4]+'.'+name_layer[-1][4:6]+'.'+name_layer[-1][6:8]): area_f_u}
                dp_vector_tulun.changeAttributeValues({f.id(): attr})
                vector_tulun.updateFields()

# запись изменения площади водной поверхности в зависимости от даты в слой кадастровых кварталов
field_tulun = vector_tulun.fields().names()
names = []
for name_field in field_tulun:
    name = name_field.split('.')
    if len(name) == 3:
        names.append(name_field)
names.sort()

for i in range(len(names)-1):
    exp = QgsExpression('"'+names[i+1]+'"-"'+names[i]+'"')
    context = QgsExpressionContext()
    context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(vector_tulun))

    # добавление поля для записи изменения площади водной поверхности в зависимости от даты в слой кадастровых кварталов
    dp_vector_tulun.addAttributes([QgsField(names[i][-2:]+names[i][-5:-3]+'-'+names[i+1][-2:]+names[i+1][-5:-3], QVariant.Double)])
    vector_tulun.updateFields()

    with edit(vector_tulun):
        for f in vector_tulun.getFeatures():
            context.setFeature(f)
            f[names[i][-2:]+names[i][-5:-3]+'-'+names[i+1][-2:]+names[i+1][-5:-3]] = exp.evaluate(context)
            vector_tulun.updateFeature(f)
