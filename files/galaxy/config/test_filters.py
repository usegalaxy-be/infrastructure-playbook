import logging
log = logging.getLogger( __name__ )


# Legacy script. Used to have the email of a developer in the list below. 
DEVELOPERS = []

def filter_test_sections( context, section ):
    """
    Filter section listed on the test_sections list for everyone except 

    """
    user = context.trans.user
    email = user and user.email
    test_sections = ['test_tools']
    return section.id not in test_sections or email in DEVELOPERS



def filter_development_tools( context, tool ):
    """
    Filter tools with version="dev" for all users except those in DEVELOPERS list

    """
    version = tool.version
    user = context.trans.user
    email = user and user.email
    return "dev" not in version or email in DEVELOPERS


