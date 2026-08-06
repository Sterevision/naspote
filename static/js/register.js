document.addEventListener('DOMContentLoaded', function () {
    var picker = document.getElementById('accountTypePicker');
    var input = document.getElementById('accountTypeInput');
    var orgFields = document.getElementById('orgFields');
    var pickerMap = null;

    picker.querySelectorAll('.vis-option').forEach(function (opt) {
        opt.addEventListener('click', function () {
            picker.querySelectorAll('.vis-option').forEach(function (o) { o.classList.remove('selected'); });
            opt.classList.add('selected');
            input.value = opt.dataset.type;

            if (opt.dataset.type === 'organization') {
                orgFields.classList.add('open');
                // лениво создаём карту, чтобы она корректно посчитала размер
                if (!pickerMap) {
                    pickerMap = initLocationPicker('orgPickerMap', 'orgLatInput', 'orgLngInput', 'orgLocateBtn', 'orgCoords', null, null);
                } else {
                    setTimeout(function () { pickerMap.invalidateSize(); }, 100);
                }
            } else {
                orgFields.classList.remove('open');
            }
        });
    });
});