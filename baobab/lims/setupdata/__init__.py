from bika.lims.exportimport.dataimport import SetupDataSetList as SDL
from bika.lims.exportimport.setupdata import WorksheetImporter
from Products.CMFCore.utils import getToolByName
from bika.lims.utils import tmpID
from Products.CMFPlone.utils import safe_unicode, _createObjectByType
from bika.lims.interfaces import ISetupDataSetList
from zope.interface import implements
from baobab.lims.idserver import renameAfterCreation
from bika.lims.workflow import doActionFor
from bika.lims import logger
from plone import api


def get_project_multi_items(context, string_elements, portal_type, portal_catalog):

    if not string_elements:
        return []

    pc = getToolByName(context, portal_catalog)

    items = []
    file_items = [x.strip() for x in string_elements.split(';')]

    for file_item in file_items:
        item_list = pc(portal_type=portal_type, Title=file_item)
        if item_list:
            items.append(item_list[0].getObject().UID())

    return items


class SetupDataSetList(SDL):

    implements(ISetupDataSetList)

    def __call__(self):
        return SDL.__call__(self, projectname="baobab.lims")


class Products(WorksheetImporter):
    """ Import test products
    """
    def Import(self):
        folder = self.context.bika_setup.bika_products
        rows = self.get_rows(3)
        bsc = getToolByName(self.context, 'bika_setup_catalog')
        suppliers = [o.getObject() for o in bsc(portal_type="Supplier")]
        for row in rows:
            title = row.get('Title')
            description = row.get('description', '')
            obj = _createObjectByType('Product', folder, tmpID())
            obj.edit(
                title=title,
                description=description,
                Hazardous=self.to_bool(row.get('Hazardous', '')),
                Quantity=self.to_int(row.get('Quantity', 0)),
                Unit=row.get('Unit', ''),
                Price=str(row.get('Price', '0.00'))
            )

            for supplier in suppliers:
                if supplier.Title() == row.get('Suppliers', ''):
                    obj.setSupplier(supplier)
                    break

            obj.unmarkCreationFlag()
            renameAfterCreation(obj)


class Kit_Components(WorksheetImporter):
    """ This class is called from Kit_Templates and not from LoadSetupData class
    """
    def __init__(self, lsd, workbook, dataset_project, dataset_name, template_name, catalog):
        self.lsd = lsd
        self.workbook = workbook
        self.dataset_project = dataset_project
        self.dataset_name = dataset_name
        self.template_name = template_name
        self.catalog = catalog
        self.product_list = []

        WorksheetImporter.__call__(self, self.lsd, self.workbook, self.dataset_project, self.dataset_name)

    def Import(self):
        rows = self.get_rows(3)
        product_obj = None
        for row in rows:
            if self.template_name == row.get('templateName'):
                product_name = row.get('componentName')

                brains = self.catalog.searchResults({'portal_type': 'Product', 'title': product_name})
                if brains and len(brains) == 1:
                    product_obj = brains[0].getObject()
                    self.product_list.append({
                        'product': product_name,
                        'product_uid': product_obj.UID(),
                        'value': '',
                        'quantity': row.get('quantity')
                    })

    def get_product_list(self):
        """ This method is called after Import to get computed product_list
        """
        return self.product_list


class Kit_Templates(WorksheetImporter):
    """ Kit_Templates worksheet contains only Kit Template without components. Components are listed in another
        worksheet (see Kit_Components class).
    """
    def Import(self):
        folder = self.context.bika_setup.bika_kittemplates
        rows = self.get_rows(3)
        catalog = getToolByName(self.context, 'bika_setup_catalog')
        for row in rows:
            template_name = row.get('templateName')
            kit_component = Kit_Components(self, self.workbook, self.dataset_project, self.dataset_name, template_name, catalog)
            product_list = kit_component.get_product_list()
            obj = _createObjectByType('KitTemplate', folder, tmpID())
            obj.edit(
                title=template_name,
                ProductList=product_list
            )

            obj.unmarkCreationFlag()
            renameAfterCreation(obj)


class Storage_Types(WorksheetImporter):
    """Add some dummy storage types
    """
    def Import(self):
        folder = self.context.bika_setup.bika_storagetypes
        rows = self.get_rows(3)
        for row in rows:
            title = row.get('title')
            description = row.get('description', '')
            obj = _createObjectByType('StorageType', folder, tmpID())
            obj.edit(
                title=title,
                description=description
            )
            obj.unmarkCreationFlag()
            renameAfterCreation(obj)

class Projects(WorksheetImporter):
    """ Import projects
    """
    def Import(self):

        pc = getToolByName(self.context, 'portal_catalog')

        rows = self.get_rows(3)
        for row in rows:
            # get the client object
            client_list = pc(portal_type="Client", Title=row.get('Client'))

            folder = client_list and client_list[0].getObject() or None
            if not folder: continue

            s_types = row.get('SampleTypes')
            a_services = row.get('AnalysisServices')
            st_objects = get_project_multi_items(self.context, s_types, 'SampleType', 'bika_setup_catalog')
            as_objects = get_project_multi_items(self.context, a_services, 'AnalysisService', 'bika_setup_catalog')

            obj = _createObjectByType('Project', folder, tmpID())
            obj.edit(
                title=row.get('title'),
                description=row.get('description'),
                StudyType=row.get('StudyType', ''),
                AgeHigh=self.to_int(row.get('AgeHigh', 0)),
                AgeLow=self.to_int(row.get('AgeLow', 0)),
                NumParticipants=self.to_int(row.get('NumParticipants', 0)),
                SampleType=st_objects,
                Service=as_objects,
                DateCreated=row.get('DateCreated', ''),
            )

            obj.unmarkCreationFlag()
            renameAfterCreation(obj)


class Biospecimens(WorksheetImporter):
    """ Import biospecimens
    """

    def Import(self):
        pc = getToolByName(self.context, 'portal_catalog')
        wf = getToolByName(self.context, 'portal_workflow')

        rows = self.get_rows(3)
        for row in rows:
            # get the project
            project_list = pc(portal_type="Project", Title=row.get('Project'))

            project = project_list and project_list[0].getObject() or None
            if not project: continue

            sampletype_list = pc(portal_type="SampleType", Title=row.get('SampleType'))
            sample_type = sampletype_list and sampletype_list[0].getObject() or None
            if not sample_type: continue

            linked_sample_list = pc(portal_type="Sample", Title=row.get('LinkedSample', ''))
            linked_sample = linked_sample_list and linked_sample_list[0].getObject() or None

            barcode = row.get('Barcode')
            if not barcode:
                continue

            try:
                volume = str(row.get('Volume'))
                float_volume = float(volume)
                if not float_volume:
                    continue
            except:
                continue

            obj = _createObjectByType('Sample', project, tmpID())

            st_loc_list = pc(portal_type='StoragePosition', Title=row.get('StorageLocation'))
            storage_location = st_loc_list and st_loc_list[0].getObject() or None

            obj.edit(
                title=row.get('title'),
                description=row.get('description'),
                Project=project,
                AllowSharing=row.get('AllowSharing'),
                SampleType=sample_type,
                StorageLocation=storage_location,
                SubjectID=row.get('SubjectID'),
                Barcode=barcode,
                Volume=volume,
                Unit=row.get('Unit'),
                LinkedSample=linked_sample,
                DateCreated=row.get('DateCreated'),
            )

            obj.unmarkCreationFlag()
            renameAfterCreation(obj)

            from baobab.lims.subscribers.sample import ObjectInitializedEventHandler
            ObjectInitializedEventHandler(obj, None)
            # doActionFor(obj, "sample_due")
            # doActionFor(obj, "receive")
            # doActionFor(storage_location, 'occupy')


class Kits(WorksheetImporter):
    """ Import projects
    """
    def Import(self):

        pc = getToolByName(self.context, 'portal_catalog')

        rows = self.get_rows(3)
        for row in rows:
            # get the project
            project_list = pc(portal_type="Project", Title=row.get('Project'))
            if project_list:
                project = project_list[0].getObject()
            else:
                continue

            #get the kit template if it exists
            bsc = getToolByName(self.context, 'bika_setup_catalog')
            kit_template_list = bsc(portal_type="KitTemplate", Title=row.get('KitTemplate'))
            kit_template = None
            if kit_template_list:
                kit_template = kit_template_list[0].getObject()

            obj = _createObjectByType('Kit', project, tmpID())
            obj.edit(
                title=row.get('title'),
                description=row.get('description'),
                Project=project,
                KitTemplate=kit_template,
                #StorageLocation=
                FormsThere=row.get('FormsThere'),
                DateCreated=row.get('DateCreated', ''),
            )

            obj.unmarkCreationFlag()
            renameAfterCreation(obj)

class Storage(WorksheetImporter):
    """
    Import storage
    """
    def Import(self):

        pc = getToolByName(self.context, 'portal_catalog')

        rows = self.get_rows(3)
        for row in rows:
            # get the type of storage
            storage_type = row.get('type')
            if storage_type not in ['StorageUnit', 'ManagedStorage', 'UnmanagedStorage']:
                continue

            # get the parent
            title = row.get('title')
            parent = self.get_parent_storage(title)
            if not parent:
                print "parent not found for %s" % title
                continue

            storage_obj = _createObjectByType(storage_type, parent, tmpID())
            storage_obj.edit(
                title=title,
            )

            if storage_type == 'ManagedStorage':
                print title
                storage_obj.edit(
                    XAxis=row.get('Rows'),
                    YAxis=row.get('Columns'),
                )

            storage_obj.unmarkCreationFlag()
            renameAfterCreation(storage_obj)

            if storage_type == 'ManagedStorage':

                for p in range(1, row.get('NumberOfPoints')+1):
                    position = api.content.create(
                        container=storage_obj,
                        type="StoragePosition",
                        id="{id}".format(id=p),  # XXX hardcoded pos title and id
                        title=title + ".{id}".format(id=p)  #would be better to get the id from the storage object.  ask hocine.
                    )
                    position.reindexObject()

    def get_parent_storage(self, title):
        pc = getToolByName(self.context, 'portal_catalog')
        title_pieces = title.split('.')

        # if len(title_pieces) <= 1:
        #     parent = self.context.bika_setup.bika_storageunit

        parent_title = '.'.join(title_pieces[:-1])
        parent_list = pc(portal_type="StorageUnit", Title=parent_title)

        if parent_list:
            parent = parent_list[0].getObject()

        return parent

